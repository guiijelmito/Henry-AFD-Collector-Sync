from playwright.sync_api import sync_playwright
import json
import os
import time
from datetime import datetime

from config import (
    URL_V1, 
    USUARIO_V1, 
    SENHA_V1, 
    DIRETORIO_DOWNLOADS,
    HEADLESS_MODE,
    SLOW_MO_MS
)

ARQUIVO_ESTADO = "estado_ponto.json"
LOTE_SEMANAL = 146  # 7 func x 4 pontos x 5 dias + 6 de gordurinha

def carregar_estado():
    if os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, "r") as f:
            return json.load(f).get("ultimo_nsr", "000044930")
    return "000044930"

def salvar_estado(novo_nsr):
    dados = {"ultimo_nsr": novo_nsr}
    with open(ARQUIVO_ESTADO, "w") as f:
        json.dump(dados, f, indent=4)
    print(f"[ESTADO] JSON atualizado com o novo NSR final: {novo_nsr}")

def automatizar_download_afd_henry():
    data_hoje = datetime.now().strftime("%d-%m-%Y")

    # 1. Leitura dinâmica do último NSR salvo
    nsr_inicial_str = carregar_estado()
    nsr_inicial_int = int(nsr_inicial_str)
    
    # 2. Cálculo dinâmico do NSR final da execução atual
    nsr_final_int = nsr_inicial_int + LOTE_SEMANAL
    
    NSR_INICIAL = f"{nsr_inicial_int:09d}"
    NSR_FINAL = f"{nsr_final_int:09d}"

    print(f"--- INICIANDO CICLO DE COLETA ---")
    print(f"Intervalo calculado: De {NSR_INICIAL} até {NSR_FINAL}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS_MODE, slow_mo=SLOW_MO_MS)
        page = browser.new_page()

        print(f"Acessando o painel do relógio em {URL_V1}...")
        page.goto(URL_V1)
        page.wait_for_load_state("networkidle")

        # Verifica se estamos na tela de login
        if page.locator("#lblLogin").is_visible():
            print("Tela de login detectada. Preenchendo credenciais...")
            page.locator("#lblLogin").fill(USUARIO_V1)
            page.locator("#lblPass").fill(SENHA_V1)
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

        # Inserindo o range de NSR dinâmico
        print(f"Inserindo range nos inputs...")
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
            
            # 3. Sucesso no download? Atualiza o estado para a próxima iteração!
            salvar_estado(NSR_FINAL)
            
        except Exception as e:
            print(f"Tentando clique direto: {e}")
            page.locator("a[onclick*='subCompD(5, 8, 1);']").click()
            time.sleep(5)
            print("Ação de salvamento concluída.")
            # Atualiza o estado mesmo no fallback se a ação concluiu
            salvar_estado(NSR_FINAL)

        time.sleep(3)
        browser.close()
        print("Automação finalizada.")

if __name__ == "__main__":
    automatizar_download_afd_henry()