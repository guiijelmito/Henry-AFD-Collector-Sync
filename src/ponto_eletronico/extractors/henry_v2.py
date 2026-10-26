import logging
import os
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

from ..config import (
    DIRETORIO_DOWNLOADS,
    HEADLESS_MODE,
    SENHA_V2,
    SLOW_MO_MS,
    URL_V2,
    USUARIO_V2,
)
from ..logging_config import capturar_screenshot

logger = logging.getLogger(__name__)


def automatizar_download_afd_v2(nsr_inicial: int, nsr_final: int) -> str:
    """Baixa o AFD do intervalo de NSR informado e retorna o caminho do arquivo salvo."""
    inicio = time.perf_counter()
    data_hoje = datetime.now().strftime("%d-%m-%Y")

    NSR_INICIAL = f"{nsr_inicial:09d}"
    NSR_FINAL = f"{nsr_final:09d}"

    nome_arquivo = f"AFD_V2_{NSR_INICIAL}_a_{NSR_FINAL}_{data_hoje}.txt"
    caminho_salvo = os.path.join(DIRETORIO_DOWNLOADS, nome_arquivo)

    logger.info("Ciclo de coleta V2 iniciado | NSR %s -> %s", NSR_INICIAL, NSR_FINAL)
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
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )

        page = browser.new_page()
        logger.debug("Navegador Chromium iniciado")

        try:
            logger.info("Acessando painel V2: %s", URL_V2)
            page.goto(URL_V2)
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
            time.sleep(3)  # buffer de estabilização
            logger.info(
                "Automação V2 finalizada com sucesso em %.1fs", time.perf_counter() - inicio
            )
            return caminho_salvo

        except Exception:
            logger.exception("Falha inesperada na automação V2")
            capturar_screenshot(page, "v2_falha_geral", logger)
            raise

        finally:
            logger.debug("Encerrando navegador V2")
            browser.close()


if __name__ == "__main__":
    from ..logging_config import setup_logging

    setup_logging()
    automatizar_download_afd_v2(int(input("NSR inicial: ")), int(input("NSR final: ")))
