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

# Caminhos base para persistência local do estado de controle de NSRs da V2
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_ESTADO = os.path.join(BASE_DIR, "estado_ponto.json")
LOTE_SEMANAL = 146  

def carregar_estado(versao="v2"):
    # Carrega o último NSR processado do arquivo JSON com fallback seguro
    if os.path.exists(ARQUIVO_ESTADO):
        try:
            with open(ARQUIVO_ESTADO, "r") as f:
                dados = json.load(f)
                if versao == "v1":
                    return dados.get("ultimo_nsr_v1")
                else:
                    return dados.get("ultimo_nsr_v2")
        except json.JSONDecodeError:
            # Silencia e prossegue para o valor padrão caso o JSON esteja corrompido
            pass 
    return "00001153"  # Valor padrão inicial para v2

def salvar_estado(novo_nsr, versao="v2"):
    # Atualiza de forma atômica o arquivo de estado preservando as demais chaves
    dados = {}
    
    # Carrega dados pré-existentes para evitar sobrescrever outras versões (ex: v1)
    if os.path.exists(ARQUIVO_ESTADO):
        try:
            with open(ARQUIVO_ESTADO, "r") as f:
                dados = json.load(f)
        except json.JSONDecodeError:
            dados = {}
            
    # Atribui o novo NSR à chave da versão correspondente
    chave = f"ultimo_nsr_{versao}"
    dados[chave] = novo_nsr
    
    # Persiste o dicionário atualizado no disco
    with open(ARQUIVO_ESTADO, "w") as f:
        json.dump(dados, f, indent=4)
        
    print(f"[ESTADO] JSON atualizado com sucesso ({chave}): {novo_nsr}")

def automatizar_download_afd_v2():
    data_hoje = datetime.now().strftime("%d-%m-%Y")

    # Define o range de NSRs baseado no último estado gravado e no lote configurado
    ultimo_nsr_v2 = carregar_estado("v2") or "1153"
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

        print(f"Acessando o painel em {URL_V2}...")
        page.goto(URL_V2)
        page.wait_for_load_state("networkidle")

        # Gerenciamento de sessão: realiza o login apenas se a tela de credenciais estiver visível
        if page.locator("#lblLogin").is_visible():
            print("Tela de login detectada. Preenchendo credenciais...")
            page.locator("#lblLogin").fill(USUARIO_V2)
            page.locator("#lblPass").fill(SENHA_V2)
            print("Executando login...")
            page.locator("a:has-text('Entrar')").click()
            page.wait_for_load_state("networkidle")
        else:
            print("Sessão já ativa detectada. Pulando etapa de autenticação...")

        # Navegação estruturada até o menu de eventos e extração
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
        
        # Preenchimento dos parâmetros de range para extração
        print(f"Inserindo range nos inputs de NSR...")
        page.locator("#lblNsrI").wait_for(state="visible", timeout=10000)
        page.locator("#lblNsrI").fill(NSR_INICIAL)
        page.locator("#lblNsrF").fill(NSR_FINAL)
        page.wait_for_load_state("networkidle")
        
        try:
            # Captura o evento de download de forma assíncrona com o clique do botão
            botao = page.locator('a[onclick="downloadData(1,32,1);"]')
            botao.scroll_into_view_if_needed()
            botao.wait_for(state="visible", timeout=10000)

            print("Botão visível! Iniciando captura do download...")
            with page.expect_download(timeout=15000) as download_info:
                botao.click()

            # Tratamento e salvamento do arquivo no diretório de destino
            download = download_info.value
            download.save_as(caminho_salvo)
            print(f"[SUCESSO] Arquivo AFD baixado e salvo em: {caminho_salvo}")
            salvar_estado(NSR_FINAL, "v2")
            
        except Exception as e:
            # Fallback defensivo caso o evento padrão de download falhe na interface
            print(f"Erro ao tentar capturar download via evento: {e}")
            print("Executando clique forçado via fallback...")
            page.locator('a[onclick="downloadData(1,32,1);"]').click(force=True)
            time.sleep(5)
            print("Ação de salvamento concluída via fallback.")
            salvar_estado(NSR_FINAL, "v2")

        # Buffer de segurança para estabilização de encerramento
        time.sleep(3)
        browser.close()
        print("Automação V2 finalizada com sucesso.")
        return caminho_salvo

if __name__ == "__main__":
    automatizar_download_afd_v2()