"""Entradas de linha de comando para execução agendada e ferramentas dev."""

from __future__ import annotations

import logging
import sys

from .logging_config import setup_logging
from .pipeline import pipeline_principal

logger = logging.getLogger(__name__)


def cli_main(argumentos: list[str] | None = None) -> int:
    """Abre o DevTools por padrão; ``--scheduled`` roda a auditoria semanal."""
    setup_logging()
    argumentos = sys.argv[1:] if argumentos is None else argumentos
    if argumentos == ["--scheduled"]:
        resultados = pipeline_principal()
        return int(any(status not in {"OK", "FORA_DA_JANELA"} for status in resultados.values()))
    if argumentos:
        logger.error("Argumento inválido: %s (use --scheduled ou nenhum argumento)", argumentos[0])
        return 2

    from .devtools import main as devtools_main

    return devtools_main()


if __name__ == "__main__":
    sys.exit(cli_main())
