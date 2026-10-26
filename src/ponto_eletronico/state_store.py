"""Persistência dos horários de auditoria das unidades V1 e V2.

O arquivo mantém somente a próxima data permitida para upload de cada unidade.
As chaves históricas de janela são aceitas durante a migração, mas não são mais
gravadas. O upload só pode ocorrer numa sexta-feira após o vencimento.
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


def audit_date_range(now: datetime | None = None) -> tuple[str, str]:
    """Retorna segunda-feira 00:00 até o momento atual, somente na sexta."""
    current_time = _current_time(now)
    if current_time.weekday() != 4:
        raise ValueError("A coleta e auditoria semanal só podem ocorrer na sexta-feira")
    monday = (current_time - timedelta(days=current_time.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (
        monday.strftime("%d/%m/%Y %H:%M"),
        current_time.strftime("%d/%m/%Y %H:%M"),
    )


def _schedule_value(data: Mapping[str, Any], version: str) -> str | None:
    value = data.get(f"next_audit_at_{version}")
    if value is None:
        value = data.get(f"next_advance_at_{version}")
    if value is None and version == "v1":
        value = data.get("next_date")
    if value is not None and not isinstance(value, str):
        raise StateIntegrityError("A próxima auditoria deve ser texto ISO-8601")
    return value


def is_audit_due(
    path: str | Path,
    version: str,
    now: datetime | None = None,
) -> bool:
    """Retorna verdadeiro somente na sexta-feira e após a data agendada."""
    if version not in {"v1", "v2"}:
        raise ValueError(f"Versão de relógio desconhecida: {version}")

    current_time = _current_time(now)
    if current_time.weekday() != 4:
        return False

    data = load_state_data(path)
    value = _schedule_value(data, version)
    if value is None:
        return True

    try:
        if len(value) == 10:
            due_at = datetime.combine(
                datetime.strptime(value, "%Y-%m-%d").date(),
                datetime_time.min,
                tzinfo=current_time.tzinfo,
            )
        else:
            due_at = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StateIntegrityError(f"Data de auditoria inválida: {value!r}") from exc

    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=current_time.tzinfo)
    else:
        due_at = due_at.astimezone(current_time.tzinfo)
    return current_time >= due_at


def record_audit_upload(
    path: str | Path,
    version: str,
    now: datetime | None = None,
) -> bool:
    """Agenda a próxima sexta-feira após upload bem-sucedido; fora da janela, não grava."""
    if version not in {"v1", "v2"}:
        raise ValueError(f"Versão de relógio desconhecida: {version}")

    current_time = _current_time(now)
    if not is_audit_due(path, version, current_time):
        return False

    data = load_state_data(path)
    # Começo da próxima sexta (00:00), não o horário exato do upload: uma tarefa
    # agendada para 00:00 rodaria segundos antes do vencimento e perderia a semana.
    next_friday = (current_time + timedelta(days=7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    data[f"next_audit_at_{version}"] = next_friday.isoformat(timespec="seconds")
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
