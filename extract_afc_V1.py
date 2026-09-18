from playwright.sync_api import sync_playwright
from datetime import datetime
import os
import time

# Importando as configurações
from config import (
    URL_V1 as URL_RELOGIO, 
    USUARIO_V1 as USUARIO_RELOGIO, 
    SENHA_V1 as SENHA_RELOGIO, 
    NSR_INICIAL, 
    NSR_FINAL, 
    DIRETORIO_DOWNLOADS,
    HEADLESS_MODE,
    SLOW_MO_MS
)

# Uso no código:

def automatizar_download_afd_henry():
    data_hoje = datetime.now().strftime("%Y-%m-%d")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS_MODE, slow_mo=SLOW_MO_MS)
        page = browser.new_page()

        print(f"Acessando o painel do relógio em {URL_RELOGIO}...")
        page.goto(URL_RELOGIO)
        page.wait_for_load_state("networkidle")

        # Verifica se estamos na tela de login
        if page.locator("#lblLogin").is_visible():
            print("Tela de login detectada. Preenchendo credenciais...")
            page.locator("#lblLogin").fill(USUARIO_RELOGIO)
            page.locator("#lblPass").fill(SENHA_RELOGIO)
            print("Executando login...")
            page.locator("a:has-text('Entrar')").click()
            page.wait_for_load_state("networkidle")
        else:
            print("Sessão já estava logada. Pulando etapa de login...")

        # Navegando até o Menu "Download"
        print("Navegando para o menu de Download...")
        page.locator("a[onclick*='subComp(0, 8, 0)']").nth(1).click()
        page.wait_for_load_state("networkidle")

        # Selecionando a opção "Filtro por NSR"
        print("Selecionando o Filtro por NSR...")
        page.locator("a[onclick*=\"navigationsa('visibleDiv', 'geral')\"]").click()
        page.wait_for_load_state("networkidle")

        # Inserindo o range de NSR
        print(f"Definindo range de NSR: De {NSR_INICIAL} até {NSR_FINAL}...")
        page.locator("#lblNsrI").fill(NSR_INICIAL)
        page.locator("#lblNsrF").fill(NSR_FINAL)

        # Interceptando o download e salvando na pasta de downloads
        print("Disparando o salvamento dos dados...")
        try:
            with page.expect_download(timeout=10000) as download_info:
                page.locator("a[onclick*='subCompD(5, 8, 1);']").click()
            
            download = download_info.value
            nome_arquivo = f"afd_nsr_{NSR_INICIAL}_a_{NSR_FINAL}_{data_hoje}.txt"
            caminho_salvo = os.path.join(DIRETORIO_DOWNLOADS, nome_arquivo)
            
            download.save_as(caminho_salvo)
            print(f"[SUCESSO] Arquivo AFD baixado e salvo em: {caminho_salvo}")
            
        except Exception as e:
            print(f"Tentando clique direto: {e}")
            page.locator("a[onclick*='subCompD(5, 8, 1);']").click()
            time.sleep(5)
            print("Ação de salvamento concluída.")

        time.sleep(3)
        browser.close()
        print("Automação finalizada.")

if __name__ == "__main__":
    automatizar_download_afd_henry()