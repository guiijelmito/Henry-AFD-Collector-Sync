from playwright.sync_api import sync_playwright
import json
import os
import time
from datetime import datetime, timedelta

from config import (
    URL_V1, 
    USUARIO_V1, 
    SENHA_V1, 
    DIRETORIO_DOWNLOADS,
    HEADLESS_MODE,
    SLOW_MO_MS
)

# Caminhos base para persistência local do estado de controle de NSRs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_ESTADO = os.path.join(BASE_DIR, "estado_ponto.json")
LOTE_SEMANAL = 146  # 7 func x 4 pontos x 5 dias + 6 de gordurinha

def carregar_estado(versao="v1"):
    # Carrega o último NSR processado do arquivo JSON com fallback seguro
    if os.path.exists(ARQUIVO_ESTADO):
        try:
            with open(ARQUIVO_ESTADO, "r") as f:
                dados = json.load(f)
                if versao == "v1":
                    return dados.get("last_nsr_v1")
                else:
                    return dados.get("last_nsr_v2")
        except json.JSONDecodeError:
            # Silencia e prossegue para o retorno padrão caso o JSON esteja corrompido
            pass 
    return "000045076"  # Valor padrão inicial para v1

def salvar_estado(novo_nsr, versao="v1"):
    # Atualiza de forma atômica o arquivo de estado preservando as demais chaves
    dados = {}
    
    # Carrega dados pré-existentes para evitar sobrescrever outras versões (ex: v2)
    if os.path.exists(ARQUIVO_ESTADO):
        try:
            with open(ARQUIVO_ESTADO, "r") as f:
                dados = json.load(f)
        except json.JSONDecodeError:
            dados = {}
            
    # Atribui o novo NSR à chave da versão correspondente
    chave = f"last_nsr_{versao}"
    
    data_coleta = dados.get("next_date")
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    
    if str(data_hoje).strip() == str(data_coleta).strip():
        print("Data da coleta")
        dados[chave] = novo_nsr
        
        proxima_data = data_hoje + timedelta(days=7)
        dados["next_date"] = proxima_data.strftime("%Y-%m-%d")
        
        # Persiste o dicionário atualizado no disco
        with open(ARQUIVO_ESTADO, "w") as f:
            json.dump(dados, f, indent=4)
        print(f"[ESTADO] JSON atualizado com sucesso ({chave}): {novo_nsr}")
        
    else:
        print("Fora da época para coleta")
        return
    
    # Persiste o dicionári'o atualizado no disco
    with open(ARQUIVO_ESTADO, "w") as f:
        json.dump(dados, f, indent=4)
    print(f"[ESTADO] JSON atualizado com sucesso ({chave}): {novo_nsr}")
    
def automatizar_download_afd_v1():
    data_hoje = datetime.now().strftime("%d-%m-%Y")

    # Define o range de NSRs baseado no último estado gravado e no lote configurado
    nsr_inicial_str = carregar_estado()
    nsr_inicial_int = int(nsr_inicial_str)
    nsr_final_int = nsr_inicial_int + LOTE_SEMANAL
    
    NSR_INICIAL = f"{nsr_inicial_int:09d}"
    NSR_FINAL = f"{nsr_final_int:09d}"

    print(f"--- INICIANDO CICLO DE COLETA V1 ---")
    print(f"Intervalo calculado: De {NSR_INICIAL} até {NSR_FINAL}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS_MODE, slow_mo=SLOW_MO_MS)
        page = browser.new_page()
        
        print(f"Acessando o painel em {URL_V1}...")
        page.goto(URL_V1)
        page.wait_for_load_state("networkidle")

# Gerenciamento de sessão: valida se a tela de login é exibida ou se já estamos autenticados
        try:
            print("Verificando estado da sessão...")
            
            # Tenta esperar pelo campo de login por até 5 segundos
            page.locator("#lblLogin").wait_for(state="visible", timeout=5000)
            print("Tela de login detectada...")
            
            # Inserção de credenciais de acesso
            print("Preenchendo credenciais...")
            page.locator("#lblLogin").fill(USUARIO_V1)  
            page.locator("#lblPass").fill(SENHA_V1)
            print("Executando login...")
            page.locator("a:has-text('Entrar')").click()
            page.wait_for_load_state("networkidle")
            
        except Exception:
            # Se o campo de login não apareceu em 5 segundos, assume que já está logado 
            # ou valida se o elemento interno da home está visível
            try:
                print("Campo de login não visível. Validando se a sessão já está ativa...")
                page.locator("a[onclick*='subComp(0, 8, 0)']").nth(1).wait_for(state="visible", timeout=5000)
                print("Sessão já autenticada com sucesso.")
            except Exception as e:
                print(f"Sessão expirada ou estado inesperado ({e}), recarregando a página...")
                page.reload()
                page.wait_for_load_state("networkidle")
                
                # Segunda tentativa de login pós-reload por segurança
                if page.locator("#lblLogin").is_visible():
                    print("Preenchendo credenciais após recarregar...")
                    page.locator("#lblLogin").fill(USUARIO_V1)  
                    page.locator("#lblPass").fill(SENHA_V1)
                    page.locator("a:has-text('Entrar')").click()
                    page.wait_for_load_state("networkidle")

        # Navegação estruturada até o menu de download de arquivos fiscais
        print("Navegando para o menu de Download...")
        menu_download = page.locator("a[onclick*='subComp(0, 8, 0)']").nth(1)
        menu_download.wait_for(state="visible", timeout=15000)
        menu_download.click()
        page.wait_for_load_state("networkidle")
        
        print("Selecionando o Filtro por NSR...")
        filtro_nsr = page.locator("a[onclick*=\"navigationsa('visibleDiv', 'geral')\"]")
        filtro_nsr.wait_for(state="visible", timeout=15000)
        filtro_nsr.click()
        page.wait_for_load_state("networkidle")

        # Preenchimento dos parâmetros de range para extração
        print(f"Inserindo range nos inputs de NSR...")
        page.locator("#lblNsrI").wait_for(state="visible", timeout=10000)
        page.locator("#lblNsrI").fill(NSR_INICIAL)
        page.locator("#lblNsrF").fill(NSR_FINAL)
        
        print("Disparando o salvamento dos dados...")
        try: 
            # Captura o evento de download de forma assíncrona com o clique do botão
            botao_baixar = page.locator("a[onclick*='subCompD(5, 8, 1);']")
            botao_baixar.scroll_into_view_if_needed()
            botao_baixar.wait_for(state="visible", timeout=10000)

            with page.expect_download(timeout=15000) as download_info:
                botao_baixar.click()
            
            # Tratamento e salvamento do arquivo no diretório de destino definido
            download = download_info.value
            nome_arquivo = f"AFD_V1_{NSR_INICIAL}_a_{NSR_FINAL}_{data_hoje}.txt"
            caminho_salvo = os.path.join(DIRETORIO_DOWNLOADS, nome_arquivo)
            
            download.save_as(caminho_salvo)
            print(f"[SUCESSO] Arquivo AFD baixado e salvo em: {caminho_salvo}")
            salvar_estado(NSR_FINAL)
        
        except Exception as e:
            # Fallback defensivo caso o evento padrão de download falhe na interface legada
            print(f"Tentando clique direto via fallback devido a: {e}")
            page.locator("a[onclick*='subCompD(5, 8, 1);']").click(force=True)
            time.sleep(5)
            caminho_salvo = os.path.join(DIRETORIO_DOWNLOADS, f"AFD_V1_{NSR_INICIAL}_a_{NSR_FINAL}_{data_hoje}.txt")
            print("Ação de salvamento via fallback concluída.")
            salvar_estado(NSR_FINAL)

        # Buffer de segurança para estabilização de encerramento
        time.sleep(3)
        browser.close()
        print("Automação V1 finalizada com sucesso.")
        return caminho_salvo

if __name__ == "__main__":
    automatizar_download_afd_v1()