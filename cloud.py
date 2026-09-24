import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Carrega as variáveis de ambiente do arquivo .env local
load_dotenv()

# Credenciais e parâmetros de conexão recuperados do ambiente
SERVER_URL = os.getenv("SERVER_URL")
SERVER_USER = os.getenv("SERVER_USER")
SERVER_PASSWORD = os.getenv("SERVER_PASSWORD")

def enviar_afd_para_servidor(caminho_arquivo_afd: str, unidade: str = "V1"):
    """Realiza o upload automatizado do arquivo AFD gerado para o painel central do servidor."""
    
    # Validação defensiva prévia: assegura que o arquivo de origem realmente existe no disco
    if not os.path.exists(caminho_arquivo_afd):
        raise FileNotFoundError(f"O arquivo AFD não foi encontrado no caminho especificado: {caminho_arquivo_afd}")

    print(f"Iniciando o processo de upload para o servidor [{unidade}]: {caminho_arquivo_afd}")

    with sync_playwright() as p:
        # Configuração dinâmica do modo de execução baseada nas variáveis de ambiente
        headless = os.getenv("HEADLESS_MODE", "False").lower() == "true"
        slow_mo = int(os.getenv("SLOW_MO_MS", "500"))
        
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        page = browser.new_page()

        try:
            print("Acessando a página de autenticação do servidor...")
            page.goto(SERVER_URL)

            # Inserção de credenciais de acesso corporativo
            page.locator("#login-user").fill(SERVER_USER)
            page.locator("#login-pswd").fill(SERVER_PASSWORD)
            
            print("Executando login no painel...")
            page.locator("button:has-text('ENTRAR')").click()
            
            # Sincronização explícita aguardando o carregamento do elemento chave pós-login
            print("Aguardando estabilização do painel administrativo...")
            page.locator("span:has-text('Upload de registros')").wait_for(state="visible", timeout=15000)
            print("Autenticação realizada com sucesso!")

            # Navegação até a aba específica de upload de arquivos fiscais
            print("Navegando para a aba 'Upload de registros'...")
            page.locator("span:has-text('Upload de registros')").click()
        
            # Anexo do arquivo AFD gerado no input do tipo file nativo
            print("Anexando o arquivo AFD ao formulário...")
            file_input = page.locator("input#upload_regs[type='file']")
            file_input.set_input_files(caminho_arquivo_afd)

            # Seleção do rádio button correspondente à unidade de ponto (ex: V1 ou V2)
            print(f"Definindo a unidade de origem como: {unidade}...")
            radio_unidade = page.locator(f"input[type='radio'][value='{unidade}']")
            radio_unidade.check()

            # Disparo da submissão do formulário
            print("Disparando envio dos dados para o servidor...")
            page.locator("button:has-text('Enviar')").click()

            # Buffer de segurança para processamento da requisição no backend do sistema
            page.wait_for_timeout(3000)
            print(f"[SUCESSO] Arquivo AFD da unidade {unidade} enviado e processado com sucesso!")

        except Exception as e:
            # Tratamento de exceção com log estruturado e propagação do erro
            print(f"[ERRO] Falha durante o processo de envio para o servidor ({unidade}): {e}")
            raise e
            
        finally:
            # Bloco finally garante o encerramento seguro do browser, mesmo em caso de falhas
            print("Encerrando instância do navegador...")
            browser.close()