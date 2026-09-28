"""Configuração central de logging do Henry AFD Collector & Sync.

- Console: formato enxuto e colorido (desenvolvimento/CLI), nível via LOG_LEVEL (padrão INFO).
- Arquivo: RotatingFileHandler com milissegundos, módulo, função e linha (produção), sempre DEBUG.
- Exceções não tratadas são registradas como CRITICAL com traceback completo.
"""
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

env_base = os.getenv("DIRETORIO_BASE")
DIRETORIO_BASE = Path(env_base) if env_base else Path(__file__).resolve().parent

LOG_DIR = Path(os.getenv("LOG_DIR", DIRETORIO_BASE / "logs"))
LOG_FILE = LOG_DIR / "afd_collector.log"
SCREENSHOT_DIR = LOG_DIR / "screenshots"

CONSOLE_FORMAT = "%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] - %(message)s"
CONSOLE_DATEFMT = "%d/%m/%Y - %H:%M:%S"
FILE_FORMAT = (
    "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | "
    "%(funcName)s:%(lineno)d | %(message)s"
)
FILE_DATEFMT = "%Y-%m-%d %H:%M:%S"

class ColorFormatter(logging.Formatter):
    """Formatter de console com cor por nível (desativa se não for TTY)."""

    RESET = "\033[0m"
    COLORS = {
        "DEBUG": "\033[36m",     # ciano
        "INFO": "\033[32m",      # verde
        "WARNING": "\033[33m",   # amarelo
        "ERROR": "\033[31m",     # vermelho
        "CRITICAL": "\033[1;41m",  # branco sobre vermelho
    }

    def __init__(self, fmt, datefmt, use_color=True):
        super().__init__(fmt, datefmt)
        self.use_color = use_color

    def format(self, record):
        original = record.levelname
        if self.use_color:
            record.levelname = f"{self.COLORS.get(original, '')}{original}{self.RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original


def _log_uncaught(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logging.getLogger("uncaught").critical(
        "Exceção não tratada encerrou o processo", exc_info=(exc_type, exc_value, exc_tb)
    )


def setup_logging() -> logging.Logger:
    """Configura o logger raiz (idempotente) e retorna-o."""
    root = logging.getLogger()
    if getattr(root, "_afd_configured", False):
        return root

    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    console.setFormatter(
        ColorFormatter(CONSOLE_FORMAT, CONSOLE_DATEFMT, use_color=sys.stdout.isatty())
    )
    root.addHandler(console)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, FILE_DATEFMT))
    root.addHandler(file_handler)

    sys.excepthook = _log_uncaught
    root._afd_configured = True
    root.debug("Logging inicializado | arquivo=%s | nível_console=%s", LOG_FILE, console.level)
    return root


def capturar_screenshot(page, tag: str, logger: logging.Logger | None = None):
    """Salva um screenshot de diagnóstico da página (uso em falhas do Playwright).

    Atenção: o screenshot pode conter dados sensíveis; restrinja o acesso a LOG_DIR.
    """
    log = logger or logging.getLogger(__name__)
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        caminho = SCREENSHOT_DIR / f"{datetime.now():%d%m%Y_%H%M%S}_{tag}.png"
        page.screenshot(path=str(caminho), full_page=True)
        log.info("Screenshot de diagnóstico salvo em %s", caminho)
        return str(caminho)
    except Exception:
        log.exception("Não foi possível capturar screenshot de diagnóstico (%s)", tag)
        return None
