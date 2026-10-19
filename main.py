"""Compatibilidade com a execução histórica via ``python main.py``."""

import sys
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from ponto_eletronico.pipeline import pipeline_principal

    results = pipeline_principal()
    return int(any(status not in {"OK", "FORA_DA_JANELA"} for status in results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
