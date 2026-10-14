"""Extrai arquivos AFD do relógio de ponto V1.

O cursor salvo define o início de um bloco fixo de NSRs. Cada execução baixa e
envia o bloco quando a janela semanal da V1 vence. Fora da janela, o pipeline
não acessa o relógio nem envia arquivo ao servidor, preservando edições manuais.
Falhas mantêm o cursor para que o mesmo bloco possa ser tentado novamente.
"""

import logging
import os
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from config import (
    DIRETORIO_DOWNLOADS,
    HEADLESS_MODE,
    SENHA_V1,
    SLOW_MO_MS,
    URL_V1,
    USUARIO_V1,
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

# Caminhos base para persistência local do estado de controle de NSRs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_ESTADO = os.path.join(BASE_DIR, "estado_ponto.json")
LOTE_SEMANAL = 146  # 7 func x 4 pontos x 5 dias + 6 de gordurinha
NSR_PADRAO_V1 = "000045076"


def carregar_estado(versao="v1"):
    """Lê e normaliza o cursor da V1, parando se o estado estiver corrompido."""
    logger.debug("Carregando estado (%s) de %s", versao, ARQUIVO_ESTADO)
    try:
        valor = load_nsr(ARQUIVO_ESTADO, versao, NSR_PADRAO_V1)
    except StateIntegrityError:
        logger.exception("Estado de coleta inválido; interrompendo para preservar o cursor")
        raise
    logger.debug("Estado carregado | last_nsr_%s=%s", versao, valor)
    return valor


def salvar_estado(novo_nsr, versao="v1"):
    """Após o envio do arquivo, avança o cursor se a janela semanal venceu.

    A data é verificada como próximo horário permitido. Execuções atrasadas
    continuam elegíveis; execuções dentro da janela deixam o cursor intacto.
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
            "Janela semanal ainda aberta; cursor %s permanece inalterado",
            versao.upper(),
        )
        return
    logger.info("Estado atualizado (last_nsr_%s=%s)", versao, novo_nsr)


def janela_semanal_vencida():
    """Informa se o pipeline pode executar a coleta e o upload da V1."""
    return is_nsr_advance_due(ARQUIVO_ESTADO, "v1", datetime.now().astimezone())


def registrar_upload_enviado():
    """Confirma no estado o lote enviado quando a janela permite avançar."""
    nsr_atual = int(carregar_estado("v1"))
    salvar_estado(f"{nsr_atual + LOTE_SEMANAL:09d}", "v1")


def automatizar_download_afd_v1():
    """Baixa o próximo bloco AFD V1; o pipeline verifica a janela antes de chamar."""
    validar_configuracao_relogio("v1")
    Path(DIRETORIO_DOWNLOADS).mkdir(parents=True, exist_ok=True)
    inicio = time.perf_counter()
    data_hoje = datetime.now().strftime("%d-%m-%Y")

    nsr_inicial_str = carregar_estado()
    nsr_inicial_int = int(nsr_inicial_str)
    nsr_final_int = nsr_inicial_int + LOTE_SEMANAL

    NSR_INICIAL = f"{nsr_inicial_int:09d}"
    NSR_FINAL = f"{nsr_final_int:09d}"

    logger.info(
        "Ciclo de coleta V1 iniciado | NSR %s -> %s (lote=%d)",
        NSR_INICIAL,
        NSR_FINAL,
        LOTE_SEMANAL,
    )
    logger.debug(
        "Parâmetros | headless=%s slow_mo=%sms destino=%s",
        HEADLESS_MODE,
        SLOW_MO_MS,
        DIRETORIO_DOWNLOADS,
    )

    caminho_salvo = os.path.join(
        DIRETORIO_DOWNLOADS, f"AFD_V1_{NSR_INICIAL}_a_{NSR_FINAL}_{data_hoje}.txt"
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
            logger.info("Acessando painel V1: %s", URL_V1)
            page.goto(URL_V1)
            page.wait_for_load_state("networkidle")

            # O relógio pode manter a sessão entre execuções; se a tela de login
            # não aparecer, confirme que o menu de download ainda está acessível.
            try:
                logger.debug("Verificando estado da sessão (timeout=5s)")
                page.locator("#lblLogin").wait_for(state="visible", timeout=5000)
                logger.info("Tela de login detectada; autenticando usuário '%s'", USUARIO_V1)
                page.locator("#lblLogin").fill(USUARIO_V1)
                page.locator("#lblPass").fill(SENHA_V1)
                page.locator("a:has-text('Entrar')").click()
                page.wait_for_load_state("networkidle")
                logger.info("Login V1 executado")

            except Exception:
                logger.info("Campo de login não visível; validando se a sessão já está ativa")
                try:
                    page.locator("a[onclick*='subComp(0, 8, 0)']").nth(1).wait_for(
                        state="visible", timeout=5000
                    )
                    logger.info("Sessão V1 já autenticada")
                except Exception:
                    logger.exception("Sessão expirada ou estado inesperado; recarregando a página")
                    page.reload()
                    page.wait_for_load_state("networkidle")

                    if page.locator("#lblLogin").is_visible():
                        logger.info("Preenchendo credenciais após recarregar a página")
                        page.locator("#lblLogin").fill(USUARIO_V1)
                        page.locator("#lblPass").fill(SENHA_V1)
                        page.locator("a:has-text('Entrar')").click()
                        page.wait_for_load_state("networkidle")
                    else:
                        logger.warning(
                            "Tela de login não apareceu após reload; seguindo sem autenticar"
                        )

            logger.info("Navegando para o menu de Download")
            menu_download = page.locator("a[onclick*='subComp(0, 8, 0)']").nth(1)
            menu_download.wait_for(state="visible", timeout=15000)
            menu_download.click()
            page.wait_for_load_state("networkidle")

            logger.info("Selecionando o filtro por NSR")
            filtro_nsr = page.locator("a[onclick*=\"navigationsa('visibleDiv', 'geral')\"]")
            filtro_nsr.wait_for(state="visible", timeout=15000)
            filtro_nsr.click()
            page.wait_for_load_state("networkidle")

            logger.info("Inserindo range de NSR: %s -> %s", NSR_INICIAL, NSR_FINAL)
            page.locator("#lblNsrI").wait_for(state="visible", timeout=10000)
            page.locator("#lblNsrI").fill(NSR_INICIAL)
            page.locator("#lblNsrF").fill(NSR_FINAL)

            logger.info("Disparando o download do AFD")
            try:
                botao_baixar = page.locator("a[onclick*='subCompD(5, 8, 1);']")
                botao_baixar.scroll_into_view_if_needed()
                botao_baixar.wait_for(state="visible", timeout=10000)

                with page.expect_download(timeout=15000) as download_info:
                    botao_baixar.click()

                download = download_info.value
                logger.debug("Download recebido | sugerido=%s", download.suggested_filename)
                download.save_as(caminho_salvo)
                logger.info("Arquivo AFD baixado e salvo em: %s", caminho_salvo)
            except Exception:
                logger.exception("Falha ao capturar ou salvar o download; o estado será preservado")
                capturar_screenshot(page, "v1_download_falha", logger)
                raise

            time.sleep(3)  # buffer de estabilização
            logger.info(
                "Automação V1 finalizada com sucesso em %.1fs", time.perf_counter() - inicio
            )
            return caminho_salvo

        except Exception:
            logger.exception("Falha inesperada na automação V1")
            if page is not None:
                capturar_screenshot(page, "v1_falha_geral", logger)
            raise

        finally:
            logger.debug("Encerrando navegador V1")
            browser.close()


if __name__ == "__main__":
    from logging_config import setup_logging

    setup_logging()
    automatizar_download_afd_v1()
