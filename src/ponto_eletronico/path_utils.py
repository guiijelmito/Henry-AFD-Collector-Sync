"""Normalização dos caminhos fornecidos por ambientes Windows e WSL."""

from __future__ import annotations

import os
from pathlib import Path


def configured_path(value: str | None, default: str | Path) -> Path:
    """Converte caminhos de ambiente para o formato nativo do host atual."""
    if not value or not value.strip():
        return Path(default).expanduser()

    text = os.path.expandvars(value.strip())
    normalized = text.replace("\\", "/")
    if (
        os.name == "nt"
        and normalized.startswith("/mnt/")
        and len(normalized) > 6
        and normalized[5].isalpha()
        and normalized[6] == "/"
    ):
        text = f"{normalized[5].upper()}:/{normalized[7:]}"
    return Path(text).expanduser()
