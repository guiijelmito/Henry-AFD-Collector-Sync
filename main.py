"""Compatibilidade com a execução histórica via ``python main.py``.

Uso:
    python main.py                       # coleta as semanas pendentes (agendamento)
    python main.py --semana 2026-10-18   # força a semana que contém essa data
"""

import argparse
import sys
from datetime import date
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Coleta AFD dos relógios V1 e V2.")
    parser.add_argument(
        "--semana",
        type=date.fromisoformat,
        help="data (AAAA-MM-DD) da semana a coletar e enviar de novo, sem alterar o estado",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from ponto_eletronico.pipeline import pipeline_principal

    return pipeline_principal(semana=args.semana)


if __name__ == "__main__":
    raise SystemExit(main())
