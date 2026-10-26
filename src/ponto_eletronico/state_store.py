"""Estado da coleta das unidades V1 e V2 (``estado_ponto.json``).

Por unidade, o arquivo guarda:

- ``ultima_semana_vX``: domingo da última semana (domingo a sábado) enviada;
- ``next_audit_at_vX``: a partir de quando a coleta é permitida (o "next_date").

As chaves antigas ``next_advance_at_vX`` e ``next_date`` são lidas na migração, e
``collected_until_vX`` é descartada.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from typing import Any

DATE_FORMAT = "%d/%m/%Y %H:%M"


class StateIntegrityError(ValueError):
    """O arquivo de estado existe, mas não pode ser interpretado com segurança."""


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


def _parse_moment(value: Any, tzinfo) -> datetime:
    """Aceita data ISO (2026-10-30) ou data e hora ISO (2026-10-30T23:59:00-03:00)."""
    if not isinstance(value, str):
        raise StateIntegrityError("Datas do estado devem ser texto ISO-8601")
    try:
        if len(value) == 10:
            moment = datetime.combine(
                datetime.strptime(value, "%Y-%m-%d").date(), datetime_time.min
            )
        else:
            moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StateIntegrityError(f"Data inválida no estado: {value!r}") from exc
    if moment.tzinfo is None:
        return moment.replace(tzinfo=tzinfo)
    return moment.astimezone(tzinfo)


def _next_audit(data: Mapping[str, Any], version: str, tzinfo) -> datetime | None:
    value = data.get(f"next_audit_at_{version}")
    if value is None:
        value = data.get(f"next_advance_at_{version}")
    if value is None and version == "v1":
        value = data.get("next_date")
    return None if value is None else _parse_moment(value, tzinfo)


def week_start(moment: datetime) -> datetime:
    """Domingo 00:00 da semana do momento informado (semanas de domingo a sábado)."""
    days_since_sunday = (moment.weekday() + 1) % 7
    return (moment - timedelta(days=days_since_sunday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def week_range(start: datetime) -> tuple[str, str]:
    """Período do filtro do relógio: domingo 00:00 até sábado 23:59."""
    end = start + timedelta(days=7) - timedelta(minutes=1)
    return start.strftime(DATE_FORMAT), end.strftime(DATE_FORMAT)


def is_audit_due(
    path: str | Path,
    version: str,
    now: datetime | None = None,
) -> bool:
    """A coleta é permitida no horário do next_audit_at da unidade ou depois dele."""
    _check_version(version)
    current_time = _current_time(now)
    due_at = _next_audit(load_state_data(path), version, current_time.tzinfo)
    return due_at is None or current_time >= due_at


def pending_weeks(
    path: str | Path,
    version: str,
    now: datetime | None = None,
    limit: int = 4,
) -> list[datetime]:
    """Domingos das semanas já encerradas que ainda não foram enviadas, em ordem.

    Começa na semana seguinte à ``ultima_semana_vX``. Sem esse valor, começa
    na última semana encerrada. Uma semana só entra depois do sábado 23:59.
    """
    _check_version(version)
    current_time = _current_time(now)
    last_sent = load_state_data(path).get(f"ultima_semana_{version}")
    if last_sent is None:
        start = week_start(current_time) - timedelta(days=7)
    else:
        start = week_start(_parse_moment(last_sent, current_time.tzinfo)) + timedelta(days=7)

    weeks = []
    while start + timedelta(days=7) <= current_time and len(weeks) < limit:
        weeks.append(start)
        start += timedelta(days=7)
    return weeks


def record_week_sent(path: str | Path, version: str, start: datetime) -> None:
    """Após o upload de uma semana, guarda-a e agenda a próxima coleta.

    O next_audit_at vira domingo 00:05 logo depois de a semana seguinte terminar.
    """
    _check_version(version)
    data = load_state_data(path)
    data[f"ultima_semana_{version}"] = start.date().isoformat()
    next_audit = start + timedelta(days=14, minutes=5)
    data[f"next_audit_at_{version}"] = next_audit.isoformat(timespec="minutes")
    for legacy_key in (f"next_advance_at_{version}", f"collected_until_{version}"):
        data.pop(legacy_key, None)
    if version == "v1":
        data.pop("next_date", None)
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
