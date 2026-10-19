"""Compatibilidade com ``python main.py`` usando o pacote em ``src``."""

import sys
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from ponto_eletronico.pipeline import pipeline_principal

    pipeline_principal()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
