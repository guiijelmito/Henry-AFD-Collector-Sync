import json
import logging
import os
import time
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright

from config import (
    URL_V1,
    USUARIO_V1,
    SENHA_V1,
    DIRETORIO_DOWNLOADS,
    HEADLESS_MODE,
    SLOW_MO_MS,
)
from logging_config import capturar_screenshot

logger = logging.getLogger(__name__)

# Caminhos base para persistência local do estado de controle de NSRs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_ESTADO = os.path.join(BASE_DIR, "estado_ponto.json")
LOTE_SEMANAL = 146  # 7 func x 4 pontos x 5 dias + 6 de gordurinha
NSR_PADRAO_V1 = "000045076"


def carregar_estado(versao="v1"):
    # Carrega o último NSR processado do arquivo JSON com fallback seguro
    logger.debug("Carregando estado (%s) de %s", versao, ARQUIVO_ESTADO)

    if not os.path.exists(ARQUIVO_ESTADO):
        logger.warning(
            "Arquivo de estado inexistente; usando NSR padrão inicial %s", NSR_PADRAO_V1
        )
        return NSR_PADRAO_V1

    try:
        with open(ARQUIVO_ESTADO, "r") as f:
            dados = json.load(f)
        chave = "last_nsr_v1" if versao == "v1" else "last_nsr_v2"
        valor = dados.get(chave)
        if valor is None:
            # FIXME: retornar None quebra o int() do chamador; considerar cair no NSR padrão
            logger.warning("Chave '%s' ausente no estado; retornando None", chave)
        else:
            logger.debug("Estado carregado | %s=%s", chave, valor)
        return valor
    except json.JSONDecodeError:
        # Risco: cair no NSR padrão pode re-baixar um intervalo já processado
        logger.exception(
            "JSON de estado corrompido; usando NSR padrão %s (possível reprocessamento)",
            NSR_PADRAO_V1,
        )
    return NSR_PADRAO_V1


def salvar_estado(novo_nsr, versao="v1"):
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
    
    data_coleta = dados.get("next_date")
    data_hoje = datetime.now()
    logger.debug("Validando janela de coleta | hoje=%s next_date=%s", data_hoje, data_coleta)

    if str(data_hoje).strip() == str(data_coleta).strip():
        logger.info("Data de coleta confirmada; atualizando estado de %s", chave)
        dados[chave] = novo_nsr

        proxima_data = data_hoje + timedelta(days=7)
        dados["next_date"] = proxima_data.strftime("%Y-%m-%d")

        with open(ARQUIVO_ESTADO, "w") as f:
            json.dump(dados, f, indent=4)
        logger.info("JSON de estado atualizado (%s): %s", chave, novo_nsr)
    else:
        logger.warning(
            "Fora da época de coleta (hoje=%s, next_date=%s); estado NÃO atualizado",
            data_hoje,
            data_coleta,
        )
        return
    
def automatizar_download_afd_v1():
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
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])
        
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
                    logger.exception(
                        "Sessão expirada ou estado inesperado; recarregando a página"
                    )
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
                salvar_estado(NSR_FINAL)

            except Exception:
                logger.exception(
                    "Falha ao capturar o evento de download; acionando fallback (clique forçado)"
                )
                capturar_screenshot(page, "v1_download_falha", logger)
                page.locator("a[onclick*='subCompD(5, 8, 1);']").click(force=True)
                time.sleep(5)
                logger.warning(
                    "Fallback concluído, mas o arquivo NÃO foi confirmado em disco: %s",
                    caminho_salvo,
                )
                # Atenção: o estado é avançado mesmo sem confirmação do arquivo
                logger.warning("Avançando estado de NSR sem confirmação de download (fallback)")
                salvar_estado(NSR_FINAL)

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
    from logging_config import setup_logging

    setup_logging()
    automatizar_download_afd_v1()
