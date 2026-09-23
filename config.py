import os
from datetime import datetime
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

# --- CREDENCIAIS E CONEXÃO DO RELÓGIO DA UNIDADE V1 ---
# Dados sensíveis puxados obrigatoriamente do .env (sem valores hardcoded)
IP_V1 = os.getenv("IP_V1")
URL_V1 = f"http://{IP_V1}"
USUARIO_V1 = os.getenv("USUARIO_V1")
SENHA_V1 = os.getenv("SENHA_V1")

# --- CREDENCIAIS E CONEXÃO DO RELÓGIO DA UNIDADE V2 ---
IP_V2 = os.getenv("IP_V2")
URL_V2 = f"http://{IP_V2}"
USUARIO_V2 = os.getenv("USUARIO_V2")
SENHA_V2 = os.getenv("SENHA_V2")

# --- DIRETÓRIOS E CAMINHOS ---
DIRETORIO_BASE = os.getenv("DIRETORIO_BASE")
DIRETORIO_DOWNLOADS = os.path.join(DIRETORIO_BASE, "afd_downloads")
os.makedirs(DIRETORIO_DOWNLOADS, exist_ok=True)

# --- CONFIGURAÇÕES DO PLAYWRIGHT ---
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "False").lower() in ("true", "1", "t")
SLOW_MO_MS = int(os.getenv("SLOW_MO_MS", "500"))