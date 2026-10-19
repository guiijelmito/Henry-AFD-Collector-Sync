"""Extrai o AFD da V1 pela janela de data/hora da semana de auditoria."""

import logging
import os
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from ..afd_validation import preencher_intervalo_data_hora, validar_afd_v1_no_intervalo
from ..config import (
    DIRETORIO_DOWNLOADS,
    HEADLESS_MODE,
    SENHA_V1,
    SLOW_MO_MS,
    URL_V1,
    USUARIO_V1,
    validar_configuracao_relogio,
)
from ..logging_config import capturar_screenshot
from ..state_store import audit_date_range, is_audit_due, record_audit_upload

logger = logging.getLogger(__name__)

# Caminho do estado de auditoria semanal da unidade
BASE_DIR = str(Path(__file__).resolve().parents[3])
ARQUIVO_ESTADO = os.path.join(BASE_DIR, "estado_ponto.json")


def janela_semanal_vencida():
    """Informa se a coleta e o upload V1 são permitidos nesta sexta-feira."""
    return is_audit_due(ARQUIVO_ESTADO, "v1", datetime.now().astimezone())


def registrar_upload_enviado():
    """Agenda a próxima auditoria V1 após upload bem-sucedido."""
    if not record_audit_upload(ARQUIVO_ESTADO, "v1", datetime.now().astimezone()):
        logger.warning("Auditoria V1 não registrada: fora da sexta-feira permitida")


def automatizar_download_afd_v1():
    """Baixa de segunda até o horário atual na janela semanal permitida."""
    validar_configuracao_relogio("v1")
    Path(DIRETORIO_DOWNLOADS).mkdir(parents=True, exist_ok=True)
    inicio = time.perf_counter()
    agora = datetime.now().astimezone()
    data_inicial, data_final = audit_date_range(agora)
    modo_headless = HEADLESS_MODE
    atraso_ms = SLOW_MO_MS
    data_inicial_arquivo = datetime.strptime(data_inicial, "%d/%m/%Y %H:%M").strftime("%Y-%m-%d")
    data_final_arquivo = datetime.strptime(data_final, "%d/%m/%Y %H:%M").strftime("%Y-%m-%d")

    logger.info(
        "Coleta V1 por data/hora iniciada | %s -> %s",
        data_inicial,
        data_final,
    )
    logger.debug(
        "Parâmetros | headless=%s slow_mo=%sms destino=%s",
        modo_headless,
        atraso_ms,
        DIRETORIO_DOWNLOADS,
    )

    caminho_salvo = os.path.join(
        DIRETORIO_DOWNLOADS,
        f"AFD_V1_{data_inicial_arquivo}_a_{data_final_arquivo}.txt",
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

            logger.info("Selecionando o filtro por data/hora")
            filtro_data_hora = page.locator(
                "a[onclick*=\"navigationsa('visibleDiv', 'communication')\"]"
            )
            filtro_data_hora.wait_for(state="visible", timeout=15000)
            filtro_data_hora.click()
            page.wait_for_load_state("networkidle")

            logger.info("Inserindo período de data/hora: %s -> %s", data_inicial, data_final)
            page.locator("#lblDataI").wait_for(state="visible", timeout=10000)
            preencher_intervalo_data_hora(
                page,
                data_inicial,
                data_final,
            )

            logger.info("Disparando o download do AFD")
            try:
                botao_baixar = page.locator("a[onclick*='subCompD(5, 8, 2);']")
                botao_baixar.scroll_into_view_if_needed()
                botao_baixar.wait_for(state="visible", timeout=10000)

                with page.expect_download(timeout=15000) as download_info:
                    botao_baixar.click()

                download = download_info.value
                logger.debug("Download recebido | sugerido=%s", download.suggested_filename)
                download.save_as(caminho_salvo)
                menor, maior, quantidade = validar_afd_v1_no_intervalo(
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
                capturar_screenshot(page, "v1_download_falha", logger)
                raise

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
    from ..logging_config import setup_logging

    setup_logging()
    automatizar_download_afd_v1()
