"""Estado da coleta das unidades V1 e V2 (``estado_ponto.json``).

Regra principal: um dia que já foi enviado ao painel nunca é enviado de novo, porque
o painel sobrescreve os registros e as correções manuais feitas depois do envio
seriam perdidas. Detalhes em ``docs/REGRAS.md``.

Por unidade, o arquivo guarda:

- ``ultimo_dia_vX``: último dia (00:00 a 23:59) enviado pela coleta agendada;
- ``dias_avulsos_vX``: dias enviados fora da fila (``--dia``/``--semana``) ou
  confirmados à mão depois de um envio duvidoso;
- ``dias_duvidosos_vX``: dias cujo upload ficou sem resposta do painel. A unidade
  para nesse dia até alguém conferir o painel e resolver.

Chaves da coleta semanal antiga, lidas só para saber o que já foi enviado:
``ultima_semana_vX`` (domingo da última semana enviada) e ``semanas_avulsas_vX``.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from typing import Any

DATE_FORMAT = "%d/%m/%Y %H:%M"

# Um dia só é considerado fechado alguns minutos depois da meia-noite, para não
# pegar uma batida de 23:59 que o relógio ainda esteja gravando.
MARGEM_FECHAMENTO = timedelta(minutes=2)

ENVIADO_AGENDADO = "enviado pela coleta agendada"
ENVIADO_AVULSO = "enviado fora da fila ou confirmado à mão"
ENVIADO_SEMANA_ANTIGA = "enviado pela coleta semanal antiga"
DUVIDOSO = "envio duvidoso aguardando conferência no painel"


class StateIntegrityError(ValueError):
    """O arquivo de estado existe, mas não pode ser interpretado com segurança."""


class DiaDuvidosoPendente(RuntimeError):
    """A fila da unidade parou num dia com envio duvidoso que ainda não foi conferido."""


def load_state_data(path: str | Path) -> dict[str, Any]:
    """Lê o JSON de estado; somente a ausência do arquivo significa estado vazio."""
    state_path = Path(path)
    try:
        with state_path.open("r", encoding="utf-8") as state_file:
            data = json.load(state_file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise StateIntegrityError(f"Arquivo de estado inválido: {state_path}") from exc

    if not isinstance(data, dict):
        raise StateIntegrityError(f"Arquivo de estado deve conter um objeto JSON: {state_path}")
    return data


def _current_time(now: datetime | None) -> datetime:
    current_time = now or datetime.now().astimezone()
    return current_time.astimezone() if current_time.tzinfo is None else current_time


def _check_version(version: str) -> None:
    if version not in {"v1", "v2"}:
        raise ValueError(f"Versão de relógio desconhecida: {version}")


def _parse_date(value: Any) -> date:
    """Aceita data ISO (2026-10-30) ou data e hora ISO; só a data importa."""
    if not isinstance(value, str):
        raise StateIntegrityError("Datas do estado devem ser texto ISO-8601")
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        return datetime.fromisoformat(value).date()
    except ValueError as exc:
        raise StateIntegrityError(f"Data inválida no estado: {value!r}") from exc


def _date_list(data: Mapping[str, Any], key: str) -> list[date]:
    values = data.get(key, [])
    if not isinstance(values, list):
        raise StateIntegrityError(f"{key} deve ser uma lista de datas")
    return [_parse_date(value) for value in values]


def day_range(day: date) -> tuple[str, str]:
    """Período do filtro do relógio: o dia das 00:00 às 23:59."""
    start = datetime.combine(day, datetime_time.min)
    end = start + timedelta(days=1) - timedelta(minutes=1)
    return start.strftime(DATE_FORMAT), end.strftime(DATE_FORMAT)


def _last_closed_day(now: datetime) -> date:
    return (now - MARGEM_FECHAMENTO).date() - timedelta(days=1)


def _last_scheduled_day(data: Mapping[str, Any], version: str) -> date | None:
    """Último dia da fila agendada, migrando da coleta semanal quando preciso."""
    value = data.get(f"ultimo_dia_{version}")
    if value is not None:
        return _parse_date(value)
    last_week = data.get(f"ultima_semana_{version}")
    if last_week is not None:
        # A semana antiga ia de domingo a sábado: o sábado foi o último dia enviado
        return _parse_date(last_week) + timedelta(days=6)
    return None


def sent_status(path: str | Path, version: str, day: date) -> str | None:
    """Diz por que o dia não pode ser enviado, ou ``None`` se ele nunca foi enviado."""
    _check_version(version)
    data = load_state_data(path)
    if day in _date_list(data, f"dias_duvidosos_{version}"):
        return DUVIDOSO
    last_scheduled = _last_scheduled_day(data, version)
    if last_scheduled is not None and day <= last_scheduled:
        return ENVIADO_AGENDADO
    if day in _date_list(data, f"dias_avulsos_{version}"):
        return ENVIADO_AVULSO
    for sunday in _date_list(data, f"semanas_avulsas_{version}"):
        if sunday <= day <= sunday + timedelta(days=6):
            return ENVIADO_SEMANA_ANTIGA
    return None


def pending_days(
    path: str | Path,
    version: str,
    now: datetime | None = None,
    limit: int = 7,
) -> list[date]:
    """Dias fechados da fila agendada da unidade, em ordem, a partir do último enviado.

    Sem nenhum registro, começa em ontem (não tenta adivinhar dias antigos). A lista
    inclui dias que já foram enviados fora da fila ou estão duvidosos: quem chama
    confere cada um com :func:`sent_status` antes de enviar.
    """
    _check_version(version)
    yesterday = _last_closed_day(_current_time(now))
    last_scheduled = _last_scheduled_day(load_state_data(path), version)
    day = yesterday if last_scheduled is None else last_scheduled + timedelta(days=1)

    days = []
    while day <= yesterday and len(days) < limit:
        days.append(day)
        day += timedelta(days=1)
    return days


def set_queue_start(path: str | Path, version: str, first_day: date) -> None:
    """Define o primeiro dia que a fila agendada da unidade vai considerar.

    Só avança a fila: voltar o ``ultimo_dia`` tiraria a proteção de dias já enviados.
    Os dias a partir de ``first_day`` continuam sendo conferidos um a um antes do envio.
    """
    _check_version(version)
    data = load_state_data(path)
    new_last = first_day - timedelta(days=1)
    current = _last_scheduled_day(data, version)
    if current is not None and new_last < current:
        raise ValueError(
            f"A fila da unidade {version.upper()} já está em {current.isoformat()}; "
            "voltar a fila poderia reenviar dias"
        )
    data[f"ultimo_dia_{version}"] = new_last.isoformat()
    write_state_data(path, data)


def record_scheduled_day(path: str | Path, version: str, day: date) -> None:
    """Avança a fila agendada até o dia informado (enviado ou já enviado antes)."""
    _check_version(version)
    data = load_state_data(path)
    data[f"ultimo_dia_{version}"] = day.isoformat()
    write_state_data(path, data)


def _add_to_list(data: dict[str, Any], key: str, day: date) -> None:
    values = data.setdefault(key, [])
    if not isinstance(values, list):
        raise StateIntegrityError(f"{key} deve ser uma lista de datas")
    if day.isoformat() not in values:
        values.append(day.isoformat())
        values.sort()


def _remove_from_list(data: dict[str, Any], key: str, day: date) -> bool:
    values = data.get(key, [])
    if not isinstance(values, list) or day.isoformat() not in values:
        return False
    values.remove(day.isoformat())
    if not values:
        data.pop(key)
    return True


def record_extra_day(path: str | Path, version: str, day: date) -> None:
    """Guarda um dia enviado fora da fila do agendamento."""
    _check_version(version)
    data = load_state_data(path)
    _add_to_list(data, f"dias_avulsos_{version}", day)
    write_state_data(path, data)


def record_doubtful_day(path: str | Path, version: str, day: date) -> None:
    """Guarda um dia cujo upload ficou sem resposta: ele não será reenviado sozinho."""
    _check_version(version)
    data = load_state_data(path)
    _add_to_list(data, f"dias_duvidosos_{version}", day)
    write_state_data(path, data)


def doubtful_days(path: str | Path, version: str) -> list[date]:
    _check_version(version)
    return _date_list(load_state_data(path), f"dias_duvidosos_{version}")


def resolve_doubtful_day(path: str | Path, version: str, day: date, *, is_in_panel: bool) -> None:
    """Resolve um dia duvidoso depois da conferência no painel.

    ``is_in_panel=True``: o dia está no painel, então ele vira enviado e nunca sobe de
    novo. ``False``: o dia não chegou ao painel e volta a poder ser enviado.
    """
    _check_version(version)
    data = load_state_data(path)
    if not _remove_from_list(data, f"dias_duvidosos_{version}", day):
        raise ValueError(f"O dia {day.isoformat()} não está duvidoso na unidade {version.upper()}")
    if is_in_panel:
        _add_to_list(data, f"dias_avulsos_{version}", day)
    write_state_data(path, data)


def write_state_data(path: str | Path, data: Mapping[str, Any]) -> None:
    """Grava o JSON por substituição atômica no mesmo diretório."""
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=state_path.parent,
            prefix=f".{state_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(data, temporary_file, indent=4, ensure_ascii=False)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, state_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
