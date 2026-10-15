"""Leitura e gravação segura do cursor de coleta de cada relógio.

O arquivo JSON compartilhado pode guardar cursores independentes da V1 e da
V2, além de metadados como ``next_date``. Ausência do arquivo significa início
de coleta; conteúdo inválido interrompe o processo para evitar sobrescrever um
cursor recuperável. As gravações substituem o arquivo por meio de um temporário
no mesmo diretório.
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
    """Indica que o arquivo de estado existe, mas não pode ser confiado."""


class NsrWindowConfigurationError(StateIntegrityError):
    """Indica que há cursor salvo, mas falta a data que libera o próximo ciclo."""


def load_state_data(path: str | Path) -> dict[str, Any]:
    """Lê o JSON de estado; só um arquivo ausente é tratado como estado vazio."""
    state_path = Path(path)
    try:
        with state_path.open("r", encoding="utf-8") as state_file:
            data = json.load(state_file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise StateIntegrityError(
            f"Arquivo de estado inválido em {state_path}; o cursor foi preservado"
        ) from exc

    if not isinstance(data, dict):
        raise StateIntegrityError(f"Arquivo de estado deve conter um objeto JSON: {state_path}")
    return data


def normalize_nsr(value: Any) -> str:
    """Valida um NSR decimal e retorna-o com pelo menos nove dígitos."""
    if isinstance(value, bool):
        raise StateIntegrityError("O NSR deve ser um número inteiro não negativo")

    text = str(value).strip()
    if not text or not text.isascii() or not text.isdigit():
        raise StateIntegrityError("O NSR deve conter apenas dígitos ASCII")
    return f"{int(text):09d}"


def load_nsr(path: str | Path, version: str, default: str) -> str:
    """Retorna o cursor da unidade em nove dígitos, aceitando o campo legado da V1.

    O campo ``ultimo_nsr`` só é consultado quando falta ``last_nsr_v1``; ele
    nunca é usado como cursor da V2.
    """
    if version not in {"v1", "v2"}:
        raise ValueError(f"Versão de relógio desconhecida: {version}")

    data = load_state_data(path)
    value = data.get(f"last_nsr_{version}")
    if value is None and version == "v1":
        value = data.get("ultimo_nsr")
    return normalize_nsr(default if value is None else value)


def save_nsr(
    path: str | Path,
    version: str,
    value: Any,
    extra_values: Mapping[str, Any] | None = None,
) -> None:
    """Atualiza um cursor sem descartar estado da outra unidade.

    ``extra_values`` permite atualizar metadados relacionados à coleta na
    mesma gravação atômica do cursor.
    """
    if version not in {"v1", "v2"}:
        raise ValueError(f"Versão de relógio desconhecida: {version}")

    data = load_state_data(path)
    data[f"last_nsr_{version}"] = normalize_nsr(value)
    if extra_values:
        data.update(extra_values)
    write_state_data(path, data)


def is_nsr_advance_due(
    path: str | Path,
    version: str,
    now: datetime | None = None,
) -> bool:
    """Informa se o cursor da unidade já pode avançar pela janela semanal.

    A data legada ``next_date`` é aceita como vencimento da V1. Sem uma data,
    um relógio sem cursor salvo está em sua primeira coleta; um cursor existente
    sem janela causa erro e bloqueia o envio até a configuração explícita.
    Datas ISO sem horário são interpretadas como início do dia no fuso local.
    """
    if version not in {"v1", "v2"}:
        raise ValueError(f"Versão de relógio desconhecida: {version}")

    current_time = now or datetime.now().astimezone()
    if current_time.tzinfo is None:
        current_time = current_time.astimezone()

    data = load_state_data(path)
    value = data.get(f"next_advance_at_{version}")
    if value is None and version == "v1":
        value = data.get("next_date")
    if value is None:
        cursor = data.get(f"last_nsr_{version}")
        if cursor is None and version == "v1":
            cursor = data.get("ultimo_nsr")
        if cursor is None:
            return True
        raise NsrWindowConfigurationError(
            f"Janela semanal do relógio {version.upper()} ausente; upload bloqueado "
            "até configurar o próximo horário permitido"
        )
    if not isinstance(value, str):
        raise StateIntegrityError("O horário de avanço deve ser texto ISO-8601")

    try:
        if len(value) == 10:
            due_date = datetime.strptime(value, "%Y-%m-%d").date()
            due_at = datetime.combine(due_date, datetime_time.min, tzinfo=current_time.tzinfo)
        else:
            due_at = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StateIntegrityError(
            f"Data de avanço inválida para o relógio {version.upper()}: {value!r}"
        ) from exc

    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=current_time.tzinfo)
    else:
        due_at = due_at.astimezone(current_time.tzinfo)
    return current_time >= due_at


def advance_nsr_after_upload(
    path: str | Path,
    version: str,
    value: Any,
    now: datetime | None = None,
) -> bool:
    """Avança o cursor e agenda sete dias após um upload sem erro.

    Retorna ``False`` quando a janela ainda está fechada. Cursor e próxima
    janela são persistidos juntos; a chave legada da V1 é removida na migração.
    """
    if version not in {"v1", "v2"}:
        raise ValueError(f"Versão de relógio desconhecida: {version}")

    current_time = now or datetime.now().astimezone()
    if current_time.tzinfo is None:
        current_time = current_time.astimezone()

    data = load_state_data(path)
    schedule_key = f"next_advance_at_{version}"

    if not is_nsr_advance_due(path, version, current_time):
        return False

    data[f"last_nsr_{version}"] = normalize_nsr(value)
    data[schedule_key] = (current_time + timedelta(days=7)).isoformat(timespec="seconds")
    if version == "v1":
        data.pop("next_date", None)
    write_state_data(path, data)
    return True


def write_state_data(path: str | Path, data: Mapping[str, Any]) -> None:
    """Grava um objeto JSON por substituição atômica no mesmo diretório."""
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
