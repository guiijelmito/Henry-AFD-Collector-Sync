import json
import logging
import os
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

from config import (
    URL_V2,
    USUARIO_V2,
    SENHA_V2,
    DIRETORIO_DOWNLOADS,
    HEADLESS_MODE,
    SLOW_MO_MS,
)
from logging_config import capturar_screenshot

logger = logging.getLogger(__name__)

# Caminhos base para persistência local do estado de controle de NSRs da V2
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_ESTADO = os.path.join(BASE_DIR, "estado_ponto.json")
LOTE_SEMANAL = 146
NSR_PADRAO_V2 = "00001153"


def carregar_estado(versao="v2"):
    # Carrega o último NSR processado do arquivo JSON com fallback seguro
    logger.debug("Carregando estado (%s) de %s", versao, ARQUIVO_ESTADO)

    if not os.path.exists(ARQUIVO_ESTADO):
        logger.warning(
            "Arquivo de estado inexistente; usando NSR padrão inicial %s", NSR_PADRAO_V2
        )
        return NSR_PADRAO_V2

    try:
        with open(ARQUIVO_ESTADO, "r") as f:
            dados = json.load(f)
        # FIXME: chaves 'last_nsr_*' aqui divergem de 'last_nsr_*' usadas no módulo V1
        chave = "last_nsr_v1" if versao == "v1" else "last_nsr_v2"
        valor = dados.get(chave)
        if valor is None:
            logger.warning("Chave '%s' ausente no estado; o chamador aplicará o padrão", chave)
        else:
            logger.debug("Estado carregado | %s=%s", chave, valor)
        return valor
    except json.JSONDecodeError:
        logger.exception(
            "JSON de estado corrompido; usando NSR padrão %s (possível reprocessamento)",
            NSR_PADRAO_V2,
        )
    return NSR_PADRAO_V2


def salvar_estado(novo_nsr, versao="v2"):
    # Atualiza o arquivo de estado preservando as demais chaves
    logger.debug("Salvando estado | versao=%s novo_nsr=%s", versao, novo_nsr)
    dados = {}

    if os.path.exists(ARQUIVO_ESTADO):
        try:
            with open(ARQUIVO_ESTADO, "r") as f:
                dados = json.load(f)
        except json.JSONDecodeError:
            logger.exception(
                "JSON de estado corrompido ao salvar; recriando estado do zero (outras chaves perdidas)"
            )
            dados = {}

    chave = f"last_nsr_{versao}"
    dados[chave] = novo_nsr

    with open(ARQUIVO_ESTADO, "w") as f:
        json.dump(dados, f, indent=4)

    logger.info("JSON de estado atualizado (%s): %s", chave, novo_nsr)


def automatizar_download_afd_v2():
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
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])
        
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
                salvar_estado(NSR_FINAL, "v2")

            except Exception:
                logger.exception(
                    "Falha ao capturar o evento de download; acionando fallback (clique forçado)"
                )
                capturar_screenshot(page, "v2_download_falha", logger)
                page.locator('a[onclick="downloadData(1,32,1);"]').click(force=True)
                time.sleep(5)
                logger.warning(
                    "Fallback concluído, mas o arquivo NÃO foi confirmado em disco: %s",
                    caminho_salvo,
                )
                logger.warning("Avançando estado de NSR sem confirmação de download (fallback)")
                salvar_estado(NSR_FINAL, "v2")

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
    from logging_config import setup_logging

    setup_logging()
    automatizar_download_afd_v2()
