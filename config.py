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

# --- INTERVALO DE NSR (Padrão) ---
NSR_INICIAL = "000044930"
NSR_FINAL = "000045076"

# --- DIRETÓRIOS E CAMINHOS ---
DIRETORIO_BASE = "/mnt/c/Users/Leticia/Documents/Dev-Verth/Relógio de Ponto"
DIRETORIO_DOWNLOADS = os.path.join(DIRETORIO_BASE, "afd_downloads")
os.makedirs(DIRETORIO_DOWNLOADS, exist_ok=True)

# --- CONFIGURAÇÕES DO PLAYWRIGHT ---
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "False").lower() in ("true", "1", "t")
SLOW_MO_MS = int(os.getenv("SLOW_MO_MS", "500"))