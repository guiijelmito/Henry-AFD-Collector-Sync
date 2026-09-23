import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

SERVER_URL = os.getenv("SERVER_URL")
SERVER_USER = os.getenv("SERVER_USER")
SERVER_PASSWORD = os.getenv("SERVER_PASSWORD")

def enviar_afd_para_servidor(caminho_arquivo_afd: str, unidade: str = "V1"):
    if not os.path.exists(caminho_arquivo_afd):
        raise FileNotFoundError(f"O arquivo AFD não foi encontrado no caminho: {caminho_arquivo_afd}")

    print(f"Iniciando o processo de upload para o servidor ({unidade}): {caminho_arquivo_afd}")

    with sync_playwright() as p:
        headless = os.getenv("HEADLESS_MODE", "False").lower() == "true"
        browser = p.chromium.launch(headless=headless, slow_mo=int(os.getenv("SLOW_MO_MS", "500")))
        page = browser.new_page()

        try:
            print("Acessando a página de login do servidor...")
            page.goto(SERVER_URL)

            page.locator("#login-user").fill(SERVER_USER)
            page.locator("#login-pswd").fill(SERVER_PASSWORD)
            
            page.locator("button:has-text('ENTRAR')").click()
            
            print("Aguardando carregamento do painel...")
            page.locator("span:has-text('Upload de registros')").wait_for(state="visible", timeout=15000)
            print("Login realizado com sucesso!")

            print("Navegando para a aba 'Upload de registros'...")
            page.locator("span:has-text('Upload de registros')").click()
        
            print("Selecionando o arquivo AFD...")
            file_input = page.locator("input#upload_regs[type='file']")
            file_input.set_input_files(caminho_arquivo_afd)

            print(f"Selecionando a unidade {unidade}...")
            radio_unidade = page.locator(f"input[type='radio'][value='{unidade}']")
            radio_unidade.check()

            print("Enviando os dados para o servidor...")
            page.locator("button:has-text('Enviar')").click()

            page.wait_for_timeout(3000)
            print(f"Arquivo AFD da unidade {unidade} enviado com sucesso para o servidor!")

        except Exception as e:
            print(f"Erro durante o processo de envio para o servidor ({unidade}): {e}")
            raise e
        finally:
            browser.close()