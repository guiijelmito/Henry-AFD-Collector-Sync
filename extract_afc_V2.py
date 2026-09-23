from playwright.sync_api import sync_playwright
import json
import os
import time
from datetime import datetime

from config import (
    URL_V2,
    USUARIO_V2,
    SENHA_V2,
    DIRETORIO_DOWNLOADS,
    HEADLESS_MODE,
    SLOW_MO_MS,
)

ARQUIVO_ESTADO = "estado_ponto.json"
LOTE_SEMANAL = 146  

def carregar_estado():
    if os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, "r") as f:
            return json.load(f).get("ultimo_nsr_v2", "00001153")
    return "00001153"

def salvar_estado(novo_nsr):
    dados = {"ultimo_nsr_v2": novo_nsr}
    with open(ARQUIVO_ESTADO, "w") as f:
        json.dump(dados, f, indent=4)
    print(f"[ESTADO] JSON atualizado com o novo NSR final: {novo_nsr}")

def automatizar_download_afd_v2():
    data_hoje = datetime.now().strftime("%d-%m-%Y")

    if os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, "r") as f:
            ultimo_nsr_v2 = json.load(f).get("ultimo_nsr_v2", "1153")
    else:
        ultimo_nsr_v2 = "1153"

    nsr_inicial_int = int(ultimo_nsr_v2)
    nsr_final_int = nsr_inicial_int + LOTE_SEMANAL
    
    NSR_INICIAL = f"{nsr_inicial_int:09d}"
    NSR_FINAL = f"{nsr_final_int:09d}"

    nome_arquivo = f"AFD_V2_{NSR_INICIAL}_a_{NSR_FINAL}_{data_hoje}.txt"
    caminho_salvo = os.path.join(DIRETORIO_DOWNLOADS, nome_arquivo)

    print(f"--- INICIANDO CICLO DE COLETA V2 ---")
    print(f"Intervalo calculado: De {NSR_INICIAL} até {NSR_FINAL}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS_MODE, slow_mo=SLOW_MO_MS)
        page = browser.new_page()

        print(f"Acessando o painel do relógio em {URL_V2}...")
        page.goto(URL_V2)
        page.wait_for_load_state("networkidle")

        if page.locator("#lblLogin").is_visible():
            print("Tela de login detectada. Preenchendo credenciais...")
            page.locator("#lblLogin").fill(USUARIO_V2)
            page.locator("#lblPass").fill(SENHA_V2)
            print("Executando login...")
            page.locator("a:has-text('Entrar')").click()
            page.wait_for_load_state("networkidle")
        else:
            print("Sessão já estava logada. Pulando etapa de login...")

        print("Navegando até o menu 'Eventos'...")
        menu_eventos = page.locator("#divMenuEvents")
        menu_eventos.wait_for(state="visible", timeout=15000)
        menu_eventos.click()
        page.wait_for_load_state("networkidle")
        
        print("Selecionando a opção 'Filtro por NSR'...")
        menu_nsr = page.locator("#menuItem1")
        menu_nsr.wait_for(state="visible", timeout=15000)
        menu_nsr.click()
        page.wait_for_load_state("networkidle")
        
        print(f"Preenchendo NSR inicial: {NSR_INICIAL} e NSR final: {NSR_FINAL}...")
        page.locator("#lblNsrI").wait_for(state="visible", timeout=10000)
        page.locator("#lblNsrI").fill(NSR_INICIAL)
        page.locator("#lblNsrF").fill(NSR_FINAL)
        page.wait_for_load_state("networkidle")
        
        try:
            botao = page.locator('a[onclick="downloadData(1,32,1);"]')
            botao.scroll_into_view_if_needed()
            botao.wait_for(state="visible", timeout=10000)

            print("Botão visível! Iniciando captura do download...")
            with page.expect_download(timeout=15000) as download_info:
                botao.click()

            download = download_info.value
            download.save_as(caminho_salvo)
            print(f"[SUCESSO] Arquivo AFD baixado e salvo em: {caminho_salvo}")
            salvar_estado(NSR_FINAL)
            
        except Exception as e:
            print(f"Erro ao tentar capturar o download via evento: {e}")
            print("Tentando clique forçado...")
            page.locator('a[onclick="downloadData(1,32,1);"]').click(force=True)
            time.sleep(5)
            print("Ação de salvamento concluída via fallback.")
            salvar_estado(NSR_FINAL)

        time.sleep(3)
        browser.close()
        print("Automação V2 finalizada.")
        return caminho_salvo

if __name__ == "__main__":
    automatizar_download_afd_v2()