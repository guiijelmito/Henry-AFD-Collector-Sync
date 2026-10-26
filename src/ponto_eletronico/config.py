"""Carrega e valida a configuração compartilhada pelas automações.

As variáveis são lidas uma vez durante a importação, depois de carregar o
arquivo ``.env``. Os módulos consumidores usam esses valores para configurar
caminhos, credenciais e o comportamento do Chromium.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
DIRETORIO_BASE = Path(os.getenv("DIRETORIO_BASE") or BASE_DIR).expanduser()
DIRETORIO_DOWNLOADS = Path(
    os.getenv("DIRETORIO_DOWNLOADS") or DIRETORIO_BASE / "afd_downloads"
).expanduser()
# O estado pode ser montado em volume persistente no Docker.
ARQUIVO_ESTADO = DIRETORIO_BASE / "estado_ponto.json"


def _url_do_relogio(nome_ip: str) -> str | None:
    endereco = os.getenv(nome_ip, "").strip()
    return f"http://{endereco}" if endereco else None


URL_V1 = _url_do_relogio("IP_V1")
USUARIO_V1 = os.getenv("USUARIO_V1")
SENHA_V1 = os.getenv("SENHA_V1")

URL_V2 = _url_do_relogio("IP_V2")
USUARIO_V2 = os.getenv("USUARIO_V2")
SENHA_V2 = os.getenv("SENHA_V2")

HEADLESS_MODE = os.getenv("HEADLESS_MODE", "false").strip().casefold() in {
    "true",
    "1",
    "t",
    "yes",
    "on",
}

try:
    SLOW_MO_MS = int(os.getenv("SLOW_MO_MS", "500"))
except ValueError as exc:
    raise ValueError("SLOW_MO_MS deve ser um inteiro não negativo") from exc

if SLOW_MO_MS < 0:
    raise ValueError("SLOW_MO_MS deve ser um inteiro não negativo")


def validar_configuracao_relogio(versao: str) -> None:
    """Falha com uma lista clara antes de iniciar o navegador."""
    configuracoes = {
        "v1": (URL_V1, USUARIO_V1, SENHA_V1),
        "v2": (URL_V2, USUARIO_V2, SENHA_V2),
    }
    try:
        valores = configuracoes[versao]
    except KeyError as exc:
        raise ValueError(f"Versão de relógio desconhecida: {versao}") from exc

    nomes = (f"IP_{versao.upper()}", f"USUARIO_{versao.upper()}", f"SENHA_{versao.upper()}")
    faltando = [nome for nome, valor in zip(nomes, valores, strict=True) if not valor]
    if faltando:
        raise OSError(f"Configuração do relógio {versao.upper()} ausente: {', '.join(faltando)}")


def _inteiro(nome: str, padrao: int) -> int:
    try:
        return int(os.getenv(nome, str(padrao)))
    except ValueError as exc:
        raise ValueError(f"{nome} deve ser um número inteiro") from exc


# Novas tentativas de download e upload quando o relógio ou o painel falham
TENTATIVAS = _inteiro("TENTATIVAS", 3)
ESPERA_ENTRE_TENTATIVAS_S = _inteiro("ESPERA_ENTRE_TENTATIVAS_S", 30)

# Alertas opcionais: sem configuração, só o relatório local é gerado
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORTA = _inteiro("SMTP_PORTA", 587)
SMTP_USUARIO = os.getenv("SMTP_USUARIO")
SMTP_SENHA = os.getenv("SMTP_SENHA")
EMAIL_ALERTA = os.getenv("EMAIL_ALERTA")
ALERTAR_SUCESSO = os.getenv("ALERTAR_SUCESSO", "true").strip().casefold() in {
    "true",
    "1",
    "t",
    "yes",
    "on",
}
