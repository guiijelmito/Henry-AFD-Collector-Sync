"""Extrai o AFD da V2 pela janela de data/hora da semana de auditoria."""

import logging
import os
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from ..afd_validation import preencher_intervalo_data_hora, validar_afd_v2_no_intervalo
from ..config import (
    DIRETORIO_DOWNLOADS,
    HEADLESS_MODE,
    SENHA_V2,
    SLOW_MO_MS,
    URL_V2,
    USUARIO_V2,
    validar_configuracao_relogio,
)
from ..logging_config import capturar_screenshot

logger = logging.getLogger(__name__)


class TailnetConnectionError(ConnectionError):
    """Indica que o painel V2 não pôde ser alcançado pela rede Tailscale."""


def automatizar_download_afd_v2(data_inicial: str, data_final: str) -> str:
    """Baixa o AFD do período informado (DD/MM/AAAA HH:MM) e devolve o caminho salvo."""
    validar_configuracao_relogio("v2")
    Path(DIRETORIO_DOWNLOADS).mkdir(parents=True, exist_ok=True)
    inicio = time.perf_counter()
    modo_headless = HEADLESS_MODE
    atraso_ms = SLOW_MO_MS
    data_inicial_arquivo = datetime.strptime(data_inicial, "%d/%m/%Y %H:%M").strftime("%Y-%m-%d")
    data_final_arquivo = datetime.strptime(data_final, "%d/%m/%Y %H:%M").strftime("%Y-%m-%d")

    nome_arquivo = f"AFD_V2_{data_inicial_arquivo}_a_{data_final_arquivo}.txt"
    caminho_salvo = os.path.join(DIRETORIO_DOWNLOADS, nome_arquivo)

    logger.info(
        "Coleta V2 por data/hora iniciada | %s -> %s",
        data_inicial,
        data_final,
    )
    logger.debug(
        "Parâmetros | headless=%s slow_mo=%sms destino=%s",
        modo_headless,
        atraso_ms,
        caminho_salvo,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=modo_headless,
            slow_mo=atraso_ms,
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
            preencher_intervalo_data_hora(
                page,
                data_inicial,
                data_final,
            )
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
                menor, maior, quantidade = validar_afd_v2_no_intervalo(
                    caminho_salvo,
                    (data_inicial, data_final),
                )
                logger.info(
                    "Filtro AFD validado | %s marcações entre %s e %s",
                    quantidade,
                    menor.strftime("%d/%m/%Y %H:%M"),
                    maior.strftime("%d/%m/%Y %H:%M"),
                )
                logger.info("Arquivo AFD baixado e salvo em: %s", caminho_salvo)
            except Exception:
                logger.exception("Falha ao capturar ou salvar o download; o estado será preservado")
                capturar_screenshot(page, "v2_download_falha", logger)
                raise

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
    from ..logging_config import setup_logging

    setup_logging()
    automatizar_download_afd_v2(input("Início (DD/MM/AAAA HH:MM): "), input("Fim: "))
