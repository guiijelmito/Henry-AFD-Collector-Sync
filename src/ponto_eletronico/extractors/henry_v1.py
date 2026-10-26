import logging
import os
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

from ..config import (
    DIRETORIO_DOWNLOADS,
    HEADLESS_MODE,
    SENHA_V1,
    SLOW_MO_MS,
    URL_V1,
    USUARIO_V1,
)
from ..logging_config import capturar_screenshot

logger = logging.getLogger(__name__)


def automatizar_download_afd_v1(nsr_inicial: int, nsr_final: int) -> str:
    """Baixa o AFD do intervalo de NSR informado e retorna o caminho do arquivo salvo."""
    inicio = time.perf_counter()
    data_hoje = datetime.now().strftime("%d-%m-%Y")

    NSR_INICIAL = f"{nsr_inicial:09d}"
    NSR_FINAL = f"{nsr_final:09d}"

    logger.info("Ciclo de coleta V1 iniciado | NSR %s -> %s", NSR_INICIAL, NSR_FINAL)
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
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )

        page = browser.new_page()
        logger.debug("Navegador Chromium iniciado")

        try:
            logger.info("Acessando painel V1: %s", URL_V1)
            page.goto(URL_V1)
            page.wait_for_load_state("networkidle")

            # Gerenciamento de sessão: tela de login ou sessão já autenticada
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
            botao_baixar = page.locator("a[onclick*='subCompD(5, 8, 1);']")
            botao_baixar.scroll_into_view_if_needed()
            botao_baixar.wait_for(state="visible", timeout=10000)

            with page.expect_download(timeout=15000) as download_info:
                botao_baixar.click()

            download = download_info.value
            logger.debug("Download recebido | sugerido=%s", download.suggested_filename)
            download.save_as(caminho_salvo)
            logger.info("Arquivo AFD baixado e salvo em: %s", caminho_salvo)
            time.sleep(3)  # buffer de estabilização
            logger.info(
                "Automação V1 finalizada com sucesso em %.1fs", time.perf_counter() - inicio
            )
            return caminho_salvo

        except Exception:
            logger.exception("Falha inesperada na automação V1")
            capturar_screenshot(page, "v1_falha_geral", logger)
            raise

        finally:
            logger.debug("Encerrando navegador V1")
            browser.close()


if __name__ == "__main__":
    from ..logging_config import setup_logging

    setup_logging()
    automatizar_download_afd_v1(int(input("NSR inicial: ")), int(input("NSR final: ")))
