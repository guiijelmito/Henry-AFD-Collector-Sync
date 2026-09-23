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
    SLOW_MO_MS
)

ARQUIVO_ESTADO = "estado_ponto.json"
LOTE_SEMANAL = 146  # 7 func x 4 pontos x

# def carregar_estado():
# def salvar_estado(novo_nsr):
def automatizar_download_afd_v2():
    data_hoje = datetime.now().strftime("%d-%m-%Y")

    # 1. Leitura dinâmica do último NSR salvo
    if os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, "r") as f:
            ultimo_nsr_v2 = json.load(f).get("ultimo_nsr_v2", "1153")
    else:
        ultimo_nsr_v2 = "1153"

    nsr_inicial_int = int(ultimo_nsr_v2)
    
    # 2. Cálculo dinâmico do NSR final da execução atual
    nsr_final_int = nsr_inicial_int + LOTE_SEMANAL
    
    NSR_INICIAL = f"{nsr_inicial_int:09d}"
    NSR_FINAL = f"{nsr_final_int:09d}"

    print(f"--- INICIANDO CICLO DE COLETA V2 ---")
    print(f"Intervalo calculado: De {NSR_INICIAL} até {NSR_FINAL}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS_MODE, slow_mo=SLOW_MO_MS)
        page = browser.new_page()

        print(f"Acessando o painel do relógio em {URL_V2}...")
        page.goto(URL_V2)
        page.wait_for_load_state("networkidle")

        # Verifica se estamos na tela de login
        if page.locator("#lblLogin").is_visible():
            print("Tela de login detectada. Preenchendo credenciais...")
            page.locator("#lblLogin").fill(USUARIO_V2)
            page.locator("#lblPass").fill(SENHA_V2)
            print("Executando login...")
            page.locator("a:has-text('Entrar')").click()
            page.wait_for_load_state("networkidle")
        else:
            print("Sessão já estava logada. Pulando etapa de login...")
            
        # Navegando até o menu "Eventos"
        print("Navegando até o menu 'Eventos'...")
        page.locator("#divMenuEvents").click()
        page.wait_for_load_state("networkidle")
        
        # Selecionando a opção "Filtro por NSR"
        print("Selecionando a opção 'Filtro por NSR'...")
        page.locator("#menuItem1").click()
        page.wait_for_load_state("networkidle")
        
        # Preenchendo os campos de NSR inicial e final
        print(f"Preenchendo NSR inicial: {NSR_INICIAL} e NSR final: {NSR_FINAL}...")
        page.locator("#lblNsrI").fill(NSR_INICIAL)
        page.locator("#lblNsrF").fill(NSR_FINAL)
        page.wait_for_load_state("networkidle")
        
        try:
            # 1. Garante que o elemento está visível e rola a tela até ele se necessário
            botao = page.locator('a[onclick="downloadData(1,32,1);"]') # Ajuste o 1 ou 2 conforme o seu HTML real
            botao.scroll_into_view_if_needed()
            
            # 2. Aguarda até que ele esteja visível de fato (com timeout de segurança)
            botao.wait_for(state="visible", timeout=10000)

            print("Botão visível! Iniciando captura do download...")
            with page.expect_download(timeout=15000) as download_info:
                botao.click()

            download = download_info.value
            nome_arquivo = f"AFD_V2_{NSR_INICIAL}_a_{NSR_FINAL}_{data_hoje}.txt"
            caminho_salvo = os.path.join(DIRETORIO_DOWNLOADS, nome_arquivo)

            download.save_as(caminho_salvo)
            print(f"[SUCESSO] Arquivo AFD baixado e salvo em: {caminho_salvo}")
            
        except Exception as e:
            print(f"Erro ao tentar capturar o download via evento: {e}")
            # Fallback: tenta clicar forçadamente ignorando verificações visuais estritas se o elemento existir
            print("Tentando clique forçado...")
            page.locator('a[onclick="downloadData(1,32,1);"]').click(force=True)
            time.sleep(5)
            print("Ação de salvamento concluída via fallback.")

        time.sleep(3)
        browser.close()
        print("Automação finalizada.")
        return caminho_salvo  # Retorna o caminho do arquivo baixado para uso posterior
    
if __name__ == "__main__":
    automatizar_download_afd_v2()