"""Automatiza o envio do arquivo AFD ao painel central via Playwright.

O módulo valida configuração e arquivo antes de abrir o navegador, autentica
no painel e envia a unidade junto ao arquivo. O envio só é considerado
confirmado quando a resposta do painel para ``POST /api/reg/upload`` chega com
status 200.

Como o painel sobrescreve os registros, a função separa dois tipos de falha:

- ``UploadRecusado``: o painel respondeu com erro 4xx (por exemplo 401 "relogar").
  Nada foi gravado, então tentar de novo é seguro.
- ``UploadSemConfirmacao``: o arquivo pode ter chegado, mas não veio resposta
  (ou veio erro 5xx). Não é seguro tentar de novo sem conferir o painel.
"""

import logging
import os
import time

from playwright.sync_api import sync_playwright

from .config import HEADLESS_MODE, SLOW_MO_MS
from .logging_config import capturar_screenshot

logger = logging.getLogger(__name__)

SERVER_URL = os.getenv("SERVER_URL", "").strip()
SERVER_USER = os.getenv("SERVER_USER")
SERVER_PASSWORD = os.getenv("SERVER_PASSWORD")

ROTA_UPLOAD = "/api/reg/upload"
ESPERA_RESPOSTA_UPLOAD_MS = 60000


class UploadRecusado(RuntimeError):
    """O painel recusou o arquivo (4xx); nada foi gravado e o envio pode ser repetido."""


class UploadSemConfirmacao(RuntimeError):
    """O arquivo pode ter sido gravado, mas o painel não confirmou; não reenviar sozinho."""


def _e_resposta_do_upload(resposta) -> bool:
    return ROTA_UPLOAD in resposta.url and resposta.request.method == "POST"


def _conferir_resposta(status: int, unidade: str) -> None:
    if status == 200:
        return
    if 400 <= status < 500:
        raise UploadRecusado(f"Painel recusou o upload da unidade {unidade} (HTTP {status})")
    raise UploadSemConfirmacao(
        f"Painel respondeu HTTP {status} ao upload da unidade {unidade}; "
        "não dá para saber se os registros foram gravados"
    )


def enviar_afd_para_servidor(caminho_arquivo_afd: str, unidade: str = "V1"):
    """Autentica no painel e submete o AFD associado à unidade informada.

    Falhas de configuração, navegação ou envio são propagadas ao pipeline
    chamador; a captura de tela é apenas diagnóstica e não oculta a exceção.
    """
    inicio = time.perf_counter()

    # Validação defensiva prévia (senha nunca é logada)
    faltando = [
        nome
        for nome, valor in (
            ("SERVER_URL", SERVER_URL),
            ("SERVER_USER", SERVER_USER),
            ("SERVER_PASSWORD", SERVER_PASSWORD),
        )
        if not valor
    ]
    if faltando:
        logger.critical("Variáveis de ambiente ausentes no .env: %s", ", ".join(faltando))
        raise OSError(f"Variáveis de ambiente ausentes: {', '.join(faltando)}")

    if not os.path.isfile(caminho_arquivo_afd):
        logger.error("Arquivo AFD não encontrado: %s", caminho_arquivo_afd)
        raise FileNotFoundError(
            f"O arquivo AFD não foi encontrado no caminho especificado: {caminho_arquivo_afd}"
        )

    tamanho = os.path.getsize(caminho_arquivo_afd)
    logger.info(
        "Iniciando upload [%s] | arquivo=%s (%d bytes)", unidade, caminho_arquivo_afd, tamanho
    )
    if tamanho == 0:
        logger.warning(
            "Arquivo AFD [%s] está vazio (0 bytes); o upload pode ser rejeitado", unidade
        )

    with sync_playwright() as p:
        browser = None
        page = None
        try:
            logger.debug(
                "Parâmetros do navegador | headless=%s slow_mo=%sms",
                HEADLESS_MODE,
                SLOW_MO_MS,
            )
            browser = p.chromium.launch(headless=HEADLESS_MODE, slow_mo=SLOW_MO_MS)
            page = browser.new_page()
            logger.info("Acessando a página de autenticação: %s", SERVER_URL)
            page.goto(SERVER_URL)

            logger.info("Executando login no painel com o usuário '%s'", SERVER_USER)
            page.locator("#login-user").fill(SERVER_USER)
            page.locator("#login-pswd").fill(SERVER_PASSWORD)
            page.locator("button:has-text('ENTRAR')").click()

            logger.debug("Aguardando estabilização do painel administrativo (timeout=15s)")
            page.locator("span:has-text('Upload de registros')").wait_for(
                state="visible", timeout=15000
            )
            logger.info("Autenticação realizada com sucesso")

            logger.info("Navegando para a aba 'Upload de registros'")
            page.locator("span:has-text('Upload de registros')").click()

            logger.debug("Anexando arquivo ao formulário")
            file_input = page.locator("input#upload_regs[type='file']")
            file_input.set_input_files(caminho_arquivo_afd)

            logger.info("Definindo a unidade de origem como %s", unidade)
            radio_unidade = page.locator(f"input[type='radio'][value='{unidade}']")
            radio_unidade.check()

            logger.info("Enviando dados ao servidor")
            botao_enviar = page.locator("button:has-text('Enviar')")
            botao_enviar.wait_for(state="visible", timeout=15000)
            try:
                with page.expect_response(
                    _e_resposta_do_upload, timeout=ESPERA_RESPOSTA_UPLOAD_MS
                ) as info_resposta:
                    botao_enviar.click()
                status = info_resposta.value.status
            except Exception as exc:
                # A partir do clique em Enviar o arquivo pode ter chegado ao painel
                raise UploadSemConfirmacao(
                    f"Sem resposta do painel ao upload da unidade {unidade}: {exc}"
                ) from exc

            _conferir_resposta(status, unidade)
            logger.info(
                "Upload da unidade %s confirmado pelo painel (HTTP 200, %.1fs)",
                unidade,
                time.perf_counter() - inicio,
            )

        except Exception:
            logger.exception("Falha durante o envio ao servidor (unidade %s)", unidade)
            if page is not None:
                capturar_screenshot(page, f"cloud_falha_{unidade}", logger)
            raise

        finally:
            if browser is not None:
                logger.debug("Encerrando instância do navegador")
                browser.close()
