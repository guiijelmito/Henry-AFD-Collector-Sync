"""Estado persistente da coleta: último NSR enviado e janela de coleta de cada unidade.

Formato de ``estado_ponto.json``::

    {
        "last_nsr_v1": "000045076",
        "last_nsr_v2": "000001153",
        "next_date_v1": "2026-10-30",
        "next_date_v2": "2026-10-30"
    }

A chave antiga ``next_date`` (compartilhada) ainda é lida como padrão das duas unidades.
"""

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

ARQUIVO_ESTADO = Path(__file__).resolve().parents[2] / "estado_ponto.json"
INTERVALO_DIAS = 7
NSR_PADRAO = {"V1": "000045076", "V2": "000001153"}


def carregar(arquivo=None):
    """Lê o estado; arquivo ausente vira estado vazio, JSON corrompido é erro (não chuta NSR)."""
    arquivo = arquivo or ARQUIVO_ESTADO
    if not os.path.exists(arquivo):
        logger.warning("Arquivo de estado inexistente (%s); usando valores padrão", arquivo)
        return {}
    with open(arquivo, encoding="utf-8") as f:
        return json.load(f)


def salvar(dados, arquivo=None):
    """Grava de forma atômica: um arquivo temporário substitui o original de uma vez."""
    arquivo = arquivo or ARQUIVO_ESTADO
    temporario = f"{arquivo}.tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4)
    os.replace(temporario, arquivo)


def ultimo_nsr(dados, unidade):
    return int(dados.get(f"last_nsr_{unidade.lower()}") or NSR_PADRAO[unidade])


def proxima_coleta(dados, unidade):
    """Data a partir da qual a unidade pode coletar (None = liberada desde já)."""
    valor = dados.get(f"next_date_{unidade.lower()}") or dados.get("next_date")
    return date.fromisoformat(str(valor).strip()[:10]) if valor else None


def coleta_liberada(dados, unidade, hoje):
    proxima = proxima_coleta(dados, unidade)
    return proxima is None or hoje >= proxima


def registrar_nsr(dados, unidade, nsr):
    dados[f"last_nsr_{unidade.lower()}"] = f"{nsr:09d}"


def avancar_janela(dados, unidade, hoje):
    """Avança a janela em passos de 7 dias a partir da data anterior, mantendo o dia da semana.

    Assim uma coleta atrasada (ex.: sábado, porque o PC estava desligado na sexta)
    não empurra as próximas coletas para sábado.
    """
    proxima = proxima_coleta(dados, unidade) or hoje
    while proxima <= hoje:
        proxima += timedelta(days=INTERVALO_DIAS)
    dados[f"next_date_{unidade.lower()}"] = proxima.isoformat()
    return proxima
