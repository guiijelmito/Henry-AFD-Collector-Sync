"""Extrai arquivos AFD do relógio V2, conectado pela rede externa.

O cursor e a janela semanal da V2 são independentes dos da V1. Cada execução
baixa e envia o bloco quando a janela vence. Fora da janela, o pipeline não
acessa o relógio nem envia arquivo ao servidor, preservando edições manuais.
Falhas mantêm o cursor para permitir nova tentativa.
"""

import logging
import os
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from config import (
    DIRETORIO_DOWNLOADS,
    HEADLESS_MODE,
    SENHA_V2,
    SLOW_MO_MS,
    URL_V2,
    USUARIO_V2,
    validar_configuracao_relogio,
)
from logging_config import capturar_screenshot
from state_store import (
    StateIntegrityError,
    advance_nsr_after_upload,
    is_nsr_advance_due,
    load_nsr,
)

logger = logging.getLogger(__name__)


class TailnetConnectionError(ConnectionError):
    """Indica que o painel V2 não pôde ser alcançado pela rede Tailscale."""


# Caminhos base para persistência local do estado de controle de NSRs da V2
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_ESTADO = os.path.join(BASE_DIR, "estado_ponto.json")
LOTE_SEMANAL = 146
NSR_PADRAO_V2 = "00001153"


def carregar_estado(versao="v2"):
    """Lê e normaliza o cursor da V2, parando se o estado estiver corrompido."""
    logger.debug("Carregando estado (%s) de %s", versao, ARQUIVO_ESTADO)
    try:
        valor = load_nsr(ARQUIVO_ESTADO, versao, NSR_PADRAO_V2)
    except StateIntegrityError:
        logger.exception("Estado de coleta inválido; interrompendo para preservar o cursor")
        raise
    logger.debug("Estado carregado | last_nsr_%s=%s", versao, valor)
    return valor


def salvar_estado(novo_nsr, versao="v2"):
    """Após o envio, avança o cursor V2 se a janela semanal venceu.

    Um estado inicial sem cursor avança no primeiro upload; cursores existentes
    sem horário de janela ficam bloqueados pelo pipeline até serem configurados.
    """
    logger.debug("Salvando estado | versao=%s novo_nsr=%s", versao, novo_nsr)
    if not advance_nsr_after_upload(
        ARQUIVO_ESTADO,
        versao,
        novo_nsr,
        now=datetime.now().astimezone(),
    ):
        logger.warning(
            "Janela semanal ainda aberta; cursor %s permanece inalterado", versao.upper()
        )
        return
    logger.info("Estado atualizado (last_nsr_%s=%s)", versao, novo_nsr)


def janela_semanal_vencida():
    """Informa se o pipeline pode executar a coleta e o upload da V2."""
    return is_nsr_advance_due(ARQUIVO_ESTADO, "v2", datetime.now().astimezone())


def registrar_upload_enviado():
    """Confirma no estado o lote enviado quando a janela permite avançar."""
    nsr_atual = int(carregar_estado("v2"))
    salvar_estado(f"{nsr_atual + LOTE_SEMANAL:09d}", "v2")


def automatizar_download_afd_v2():
    """Baixa o próximo bloco AFD V2; o pipeline verifica a janela antes de chamar."""
    validar_configuracao_relogio("v2")
    Path(DIRETORIO_DOWNLOADS).mkdir(parents=True, exist_ok=True)
    inicio = time.perf_counter()
    data_hoje = datetime.now().strftime("%d-%m-%Y")

    ultimo_nsr_v2 = carregar_estado("v2") or "1153"
    nsr_inicial_int = int(ultimo_nsr_v2)
    nsr_final_int = nsr_inicial_int + LOTE_SEMANAL

    NSR_INICIAL = f"{nsr_inicial_int:09d}"
    NSR_FINAL = f"{nsr_final_int:09d}"

    nome_arquivo = f"AFD_V2_{NSR_INICIAL}_a_{NSR_FINAL}_{data_hoje}.txt"
    caminho_salvo = os.path.join(DIRETORIO_DOWNLOADS, nome_arquivo)

    logger.info(
        "Ciclo de coleta V2 iniciado | NSR %s -> %s (lote=%d)",
        NSR_INICIAL,
        NSR_FINAL,
        LOTE_SEMANAL,
    )
    logger.debug(
        "Parâmetros | headless=%s slow_mo=%sms destino=%s",
        HEADLESS_MODE,
        SLOW_MO_MS,
        caminho_salvo,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS_MODE,
            slow_mo=SLOW_MO_MS,
        )
        page = None

        try:
            page = browser.new_page()
            logger.debug("Navegador Chromium iniciado")
            logger.info("Acessando painel V2: %s", URL_V2)
            try:
                page.goto(URL_V2)
            except PlaywrightError as exc:
                raise TailnetConnectionError(
                    "Não foi possível alcançar o painel V2. Verifique se o dispositivo está "
                    "conectado ao Tailscale, se o IP_V2 está correto e se o relógio está acessível."
                ) from exc
            page.wait_for_load_state("networkidle")

            if page.locator("#lblLogin").is_visible():
                logger.info("Tela de login detectada; autenticando usuário '%s'", USUARIO_V2)
                page.locator("#lblLogin").fill(USUARIO_V2)
                page.locator("#lblPass").fill(SENHA_V2)
                page.locator("a:has-text('Entrar')").click()
                page.wait_for_load_state("networkidle")
                logger.info("Login V2 executado")
            else:
                logger.info("Sessão V2 já ativa; pulando autenticação")

            logger.info("Navegando até o menu 'Eventos'")
            menu_eventos = page.locator("#divMenuEvents")
            menu_eventos.wait_for(state="visible", timeout=15000)
            menu_eventos.click()
            page.wait_for_load_state("networkidle")

            logger.info("Selecionando a opção 'Filtro por NSR'")
            menu_nsr = page.locator("#menuItem1")
            menu_nsr.wait_for(state="visible", timeout=15000)
            menu_nsr.click()
            page.wait_for_load_state("networkidle")

            logger.info("Inserindo range de NSR: %s -> %s", NSR_INICIAL, NSR_FINAL)
            page.locator("#lblNsrI").wait_for(state="visible", timeout=10000)
            page.locator("#lblNsrI").fill(NSR_INICIAL)
            page.locator("#lblNsrF").fill(NSR_FINAL)
            page.wait_for_load_state("networkidle")

            try:
                botao = page.locator('a[onclick="downloadData(1,32,1);"]')
                botao.scroll_into_view_if_needed()
                botao.wait_for(state="visible", timeout=10000)

                logger.debug("Botão de download visível; iniciando captura")
                with page.expect_download(timeout=15000) as download_info:
                    botao.click()

                download = download_info.value
                logger.debug("Download recebido | sugerido=%s", download.suggested_filename)
                download.save_as(caminho_salvo)
                logger.info("Arquivo AFD baixado e salvo em: %s", caminho_salvo)
            except Exception:
                logger.exception("Falha ao capturar ou salvar o download; o estado será preservado")
                capturar_screenshot(page, "v2_download_falha", logger)
                raise

            time.sleep(3)  # buffer de estabilização
            logger.info(
                "Automação V2 finalizada com sucesso em %.1fs", time.perf_counter() - inicio
            )
            return caminho_salvo

        except TailnetConnectionError:
            if page is not None:
                capturar_screenshot(page, "v2_conexao_tailscale_falha", logger)
            raise

        except Exception:
            logger.exception("Falha inesperada na automação V2")
            if page is not None:
                capturar_screenshot(page, "v2_falha_geral", logger)
            raise

        finally:
            logger.debug("Encerrando navegador V2")
            browser.close()


if __name__ == "__main__":
    from logging_config import setup_logging

    setup_logging()
    automatizar_download_afd_v2()
