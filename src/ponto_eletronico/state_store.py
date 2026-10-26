"""Estado da coleta das unidades V1 e V2 (``estado_ponto.json``).

Por unidade, o arquivo guarda:

- ``next_audit_at_vX``: a partir de quando o upload é permitido (o "next_date");
- ``collected_until_vX``: até que data e hora a última coleta enviada chegou.

As chaves antigas ``next_advance_at_vX`` e ``next_date`` são lidas na migração.
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


def is_audit_due(
    path: str | Path,
    version: str,
    now: datetime | None = None,
) -> bool:
    """O upload é permitido no horário do next_audit_at da unidade ou depois dele."""
    _check_version(version)
    current_time = _current_time(now)
    due_at = _next_audit(load_state_data(path), version, current_time.tzinfo)
    return due_at is None or current_time >= due_at


def audit_date_range(
    path: str | Path,
    version: str,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Período a coletar: de onde a última coleta parou (ou segunda 00:00) até agora.

    Começar onde a anterior parou garante que nenhuma marcação fique de fora,
    mesmo que uma coleta atrase ou falhe por alguns dias.
    """
    _check_version(version)
    current_time = _current_time(now)
    collected_until = load_state_data(path).get(f"collected_until_{version}")
    if collected_until is None:
        start = (current_time - timedelta(days=current_time.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:
        start = _parse_moment(collected_until, current_time.tzinfo)
    return start.strftime(DATE_FORMAT), current_time.strftime(DATE_FORMAT)


def record_audit_upload(
    path: str | Path,
    version: str,
    collected_until: str,
    now: datetime | None = None,
) -> bool:
    """Após upload bem-sucedido, guarda até onde coletou e agenda a próxima auditoria.

    A próxima auditoria anda de 7 em 7 dias a partir da anterior, mantendo o dia
    e a hora configurados (ex.: toda sexta às 23:59) mesmo se esta coleta atrasou.
    """
    _check_version(version)
    current_time = _current_time(now)
    data = load_state_data(path)
    due_at = _next_audit(data, version, current_time.tzinfo)
    if due_at is not None and current_time < due_at:
        return False

    next_audit = due_at or current_time
    while next_audit <= current_time:
        next_audit += timedelta(days=7)

    end = datetime.strptime(collected_until, DATE_FORMAT).replace(tzinfo=current_time.tzinfo)
    data[f"collected_until_{version}"] = end.isoformat(timespec="minutes")
    data[f"next_audit_at_{version}"] = next_audit.isoformat(timespec="minutes")
    data.pop(f"next_advance_at_{version}", None)
    if version == "v1":
        data.pop("next_date", None)
    write_state_data(path, data)
    return True


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
