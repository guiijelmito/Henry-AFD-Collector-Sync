"""Compatibilidade com a execução histórica via ``python main.py``."""

import sys
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from ponto_eletronico.main import cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
