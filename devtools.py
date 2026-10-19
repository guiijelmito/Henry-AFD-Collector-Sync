"""Atalho de compatibilidade para as ferramentas manuais de desenvolvimento."""

import sys
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from ponto_eletronico.devtools import main as run_devtools

    return run_devtools()


if __name__ == "__main__":
    raise SystemExit(main())
