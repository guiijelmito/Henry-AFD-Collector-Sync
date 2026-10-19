"""Extrai o AFD da V2 pela janela de data/hora da semana de auditoria."""

import logging
import os
import time
from datetime import datetime, timedelta
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
from state_store import audit_date_range, is_audit_due, record_audit_upload

logger = logging.getLogger(__name__)


class TailnetConnectionError(ConnectionError):
    """Indica que o painel V2 não pôde ser alcançado pela rede Tailscale."""


# Caminho do estado de auditoria semanal da unidade
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_ESTADO = os.path.join(BASE_DIR, "estado_ponto.json")


def janela_semanal_vencida():
    """Informa se a coleta e o upload V2 são permitidos nesta sexta-feira."""
    return is_audit_due(ARQUIVO_ESTADO, "v2", datetime.now().astimezone())


def registrar_upload_enviado():
    """Agenda a próxima auditoria V2 após upload bem-sucedido."""
    if not record_audit_upload(ARQUIVO_ESTADO, "v2", datetime.now().astimezone()):
        logger.warning("Auditoria V2 não registrada: fora da sexta-feira permitida")


def automatizar_download_afd_v2():
    """Baixa os registros V2 de segunda-feira até agora na sexta de auditoria."""
    validar_configuracao_relogio("v2")
    Path(DIRETORIO_DOWNLOADS).mkdir(parents=True, exist_ok=True)
    inicio = time.perf_counter()
    agora = datetime.now().astimezone()
    data_inicial, data_final = audit_date_range(agora)
    segunda_data = (agora - timedelta(days=agora.weekday())).strftime("%Y-%m-%d")
    data_hoje = agora.strftime("%Y-%m-%d")

    nome_arquivo = f"AFD_V2_{segunda_data}_a_{data_hoje}.txt"
    caminho_salvo = os.path.join(DIRETORIO_DOWNLOADS, nome_arquivo)

    logger.info(
        "Coleta V2 por data/hora iniciada | %s -> %s",
        data_inicial,
        data_final,
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

            logger.info("Selecionando a opção 'Filtro por data/hora'")
            menu_data_hora = page.locator("#menuItem2")
            menu_data_hora.wait_for(state="visible", timeout=15000)
            menu_data_hora.click()
            page.wait_for_load_state("networkidle")

            logger.info("Inserindo período de data/hora: %s -> %s", data_inicial, data_final)
            page.locator("#lblDataI").wait_for(state="visible", timeout=10000)
            page.locator("#lblDataI").fill(data_inicial)
            page.locator("#lblDataF").fill(data_final)
            page.wait_for_load_state("networkidle")

            try:
                botao = page.locator('a[onclick="downloadData(1,32,2);"]')
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
