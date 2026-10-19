"""Normalização de caminhos configurados para Windows e WSL."""

from __future__ import annotations

import os
from pathlib import Path


def configured_path(value: str | None, default: str | Path) -> Path:
    """Converte valores de caminho do ambiente em caminhos nativos do host."""
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
