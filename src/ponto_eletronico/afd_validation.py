"""Validação mínima dos registros AFD retornados pelos relógios."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import Page


class AFDRangeValidationError(ValueError):
    """O arquivo baixado não contém marcações válidas no intervalo solicitado."""


def preencher_filtro_data_hora(page: Page, seletor: str, valor: str) -> None:
    """Digita os dígitos no filtro mascarado e confere o texto formatado."""
    data_hora_esperada = datetime.strptime(valor, "%d/%m/%Y %H:%M")
    digitos = data_hora_esperada.strftime("%d%m%y%H%M")
    campo = page.locator(seletor)
    campo.press("Control+A")
    campo.press_sequentially(digitos, delay=75)
    campo.press("Tab")
    valor_aplicado = campo.input_value()
    valor_esperado = data_hora_esperada.strftime("%d/%m/%y %H:%M")
    if valor_aplicado != valor_esperado:
        raise ValueError(
            f"O campo {seletor} não manteve o formato DD/MM/AA HH:MM "
            f"(esperado={valor_esperado!r}, aplicado={valor_aplicado!r})"
        )


def preencher_intervalo_data_hora(
    page: Page,
    inicio: str,
    fim: str,
) -> None:
    """Preenche os campos mascarados de data/hora inicial e final."""
    preencher_filtro_data_hora(page, "#lblDataI", inicio)
    preencher_filtro_data_hora(page, "#lblDataF", fim)


def _validar_marcacoes_no_intervalo(
    marcacoes: list[datetime],
    intervalo: tuple[str, str],
) -> tuple[datetime, datetime, int]:
    inicio = datetime.strptime(intervalo[0], "%d/%m/%Y %H:%M")
    # O filtro tem precisão de minuto; a V2 grava segundos (10:15:30 cabe em "10:15")
    fim = datetime.strptime(intervalo[1], "%d/%m/%Y %H:%M") + timedelta(seconds=59)
    if not marcacoes:
        raise AFDRangeValidationError("O arquivo não contém registros de marcação AFD válidos")

    fora_do_intervalo = [marcacao for marcacao in marcacoes if not inicio <= marcacao <= fim]
    if fora_do_intervalo:
        menor = min(marcacoes).strftime("%d/%m/%Y %H:%M")
        maior = max(marcacoes).strftime("%d/%m/%Y %H:%M")
        raise AFDRangeValidationError(
            f"O painel retornou {len(fora_do_intervalo)} marcação(ões) fora do intervalo "
            f"solicitado; datas no arquivo: {menor} a {maior}"
        )

    return min(marcacoes), max(marcacoes), len(marcacoes)


def validar_afd_v1_no_intervalo(
    caminho: str | Path,
    intervalo: tuple[str, str],
) -> tuple[datetime, datetime, int]:
    """Lê marcações do layout V1 (DDMMYYYY e HHMM em campos fixos)."""
    marcacoes: list[datetime] = []
    conteudo = Path(caminho).read_text(encoding="utf-8", errors="replace")
    for linha in conteudo.splitlines():
        if len(linha) < 22 or not linha[:9].isdigit() or linha[9] != "3":
            continue
        try:
            marcacoes.append(datetime.strptime(f"{linha[10:18]} {linha[18:22]}", "%d%m%Y %H%M"))
        except ValueError:
            continue
    return _validar_marcacoes_no_intervalo(marcacoes, intervalo)


def validar_afd_v2_no_intervalo(
    caminho: str | Path,
    intervalo: tuple[str, str],
) -> tuple[datetime, datetime, int]:
    """Lê marcações do layout V2, cuja data/hora vem em timestamp ISO-8601."""
    marcacoes: list[datetime] = []
    conteudo = Path(caminho).read_text(encoding="utf-8", errors="replace")
    for linha in conteudo.splitlines():
        if len(linha) < 35 or not linha[:9].isdigit() or linha[9] != "3":
            continue
        match = re.match(
            r"^\d{9}3(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})",
            linha,
        )
        if match is None:
            continue
        try:
            marcacoes.append(datetime.fromisoformat(match.group(1)))
        except ValueError:
            continue
    return _validar_marcacoes_no_intervalo(marcacoes, intervalo)
