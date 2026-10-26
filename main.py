"""Compatibilidade com ``python main.py`` usando o pacote em ``src``."""

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta e envio dos AFDs dos relógios de ponto.")
    parser.add_argument(
        "--forcar",
        action="store_true",
        help="coleta mesmo antes da data liberada (next_date) no estado_ponto.json",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from ponto_eletronico.pipeline import pipeline_principal

    return pipeline_principal(forcar=args.forcar)


if __name__ == "__main__":
    raise SystemExit(main())
