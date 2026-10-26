"""Compatibilidade com a execução histórica via ``python main.py``."""

import sys
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from ponto_eletronico.pipeline import pipeline_principal

    return pipeline_principal()


if __name__ == "__main__":
    raise SystemExit(main())
