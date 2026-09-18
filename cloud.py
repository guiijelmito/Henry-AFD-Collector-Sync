import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Carrega as variáveis de ambiente
load_dotenv()

# Credenciais do Servidor PHP (adicione estas chaves no seu .env)
SERVER_URL = os.getenv("SERVER_URL")
SERVER_USER = os.getenv("SERVER_USER")
SERVER_PASSWORD = os.getenv("SERVER_PASSWORD")
caminho_exemplo_afd = Path(os.getenv("caminho_exemplo_afd")) as caminho_arquivo_afd

def enviar_afd_para_servidor(caminho_arquivo_afd: str):
    """
    Realiza o login no painel web, navega até a aba de upload,
    seleciona o arquivo AFD baixado, marca a unidade V1 e envia.
    """
    if not os.path.exists(caminho_arquivo_afd):
        raise FileNotFoundError(f"O arquivo AFD não foi encontrado no caminho: {caminho_arquivo_afd}")

    print(f"Iniciando o processo de upload para o servidor: {caminho_arquivo_afd}")

    with sync_playwright() as p:
        # Configuração do browser (respeitando o modo headless do config/env)
        headless = os.getenv("HEADLESS_MODE", "False").lower() == "true"
        browser = p.chromium.launch(headless=False, slow_mo=int(os.getenv("SLOW_MO_MS", "500")))
        page = browser.new_page()

        try:
            # Passo 1: Acessar a página de login e autenticar
            print("Acessando a página de login do servidor...")
            page.goto(SERVER_URL)

            page.locator("#login-user").fill(SERVER_USER)
            page.locator("#login-pswd").fill(SERVER_PASSWORD)
            
            # Clica no botão ENTRAR
            page.locator("button:has-text('ENTRAR')").click()
            
            # Aguarda o carregamento pós-login (ajuste o seletor conforme a home do painel)
            # Correção: Em vez de esperar por uma URL fixa de dashboard, 
            # aguardamos a aparição de um elemento único da barra lateral ou da página interna (ex: a aba "Upload de registros")
            print("Aguardando carregamento do painel...")
            page.locator("span:has-text('Upload de registros')").wait_for(state="visible", timeout=15000)
            print("Login realizado com sucesso!")

            # Passo 2: Clicar na aba "Upload de registros" (já visível)
            print("Navegando para a aba 'Upload de registros'...")
            page.locator("span:has-text('Upload de registros')").click()
        
            # Passo 3: Inserir o arquivo no input type="file" escondido
            # O Playwright lida perfeitamente com inputs file ocultos via set_input_files
            print("Selecionando o arquivo AFD...")
            file_input = page.locator("input#upload_regs[type='file']")
            file_input.set_input_files(caminho_arquivo_afd)

            # Passo 4: Selecionar a option V1 (radio button)
            print("Selecionando a unidade V1...")
            # Como o input de rádio possui value="V1", podemos localizá-lo diretamente por esse atributo
            radio_v1 = page.locator("input[type='radio'][value='V1']")
            radio_v1.check()

            # Passo 5: Clicar no botão Enviar
            print("Enviando os dados para o servidor...")
            page.locator("button:has-text('Enviar')").click()

            # Aguardar uma confirmação visual ou de rede (ajuste conforme o comportamento do seu sistema)
            page.wait_for_timeout(3000)
            print("Arquivo AFD enviado com sucesso para o servidor!")

        except Exception as e:
            print(f"Erro durante o processo de envio para o servidor: {e}")
            raise e
        finally:
            browser.close()

if __name__ == "__main__":
    # Exemplo de uso
    enviar_afd_para_servidor(str(caminho_exemplo_afd))