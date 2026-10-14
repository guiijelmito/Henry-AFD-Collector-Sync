"""Orquestra extração e upload para os relógios V1 e V2.

Cada unidade é processada mesmo que a anterior falhe. O resultado agregado
permite que a execução de linha de comando termine com código diferente de
zero se houver falha ou ausência de arquivo em qualquer relógio.
"""

import logging
import os
import sys
import time

from logging_config import setup_logging

setup_logging()  # antes dos demais módulos do projeto emitirem logs

from cloud import enviar_afd_para_servidor  # noqa: E402
from extract_afc_v1 import automatizar_download_afd_v1  # noqa: E402
from extract_afc_v2 import automatizar_download_afd_v2  # noqa: E402

logger = logging.getLogger(__name__)


def _processar_unidade(unidade, etapa, funcao_extracao, dica_falha=""):
    """Executa extração e upload, convertendo o resultado em um status do pipeline.

    A exceção da unidade é registrada e convertida em ``FALHA`` para permitir
    que a outra unidade também seja processada.
    """
    logger.info("[%s] Processando unidade %s", etapa, unidade)
    inicio = time.perf_counter()
    try:
        caminho_afd = funcao_extracao()

        if caminho_afd and os.path.exists(caminho_afd):
            enviar_afd_para_servidor(caminho_afd, unidade=unidade)
            logger.info(
                "Unidade %s processada e enviada com sucesso em %.1fs",
                unidade,
                time.perf_counter() - inicio,
            )
            return "OK"

        logger.warning(
            "Nenhum arquivo AFD válido foi gerado para a %s (caminho esperado: %s)",
            unidade,
            caminho_afd,
        )
        return "SEM_ARQUIVO"

    except Exception:
        logger.exception("Falha crítica no pipeline da unidade %s. %s", unidade, dica_falha)
        return "FALHA"


def pipeline_principal() -> dict[str, str]:
    """Processa V1 e V2 em sequência e retorna um status por unidade."""
    logger.info("=== Iniciando pipeline completo de ponto eletrônico (V1 & V2) ===")
    inicio = time.perf_counter()

    resultados = {
        "V1": _processar_unidade("V1", "1/2", automatizar_download_afd_v1),
        "V2": _processar_unidade(
            "V2",
            "2/2",
            automatizar_download_afd_v2,
            dica_falha="Galpão externo via Tailscale: verifique conexão/IP.",
        ),
    }

    duracao = time.perf_counter() - inicio
    resumo = " | ".join(f"{u}={s}" for u, s in resultados.items())
    if all(s == "OK" for s in resultados.values()):
        logger.info("=== Pipeline finalizado em %.1fs | %s ===", duracao, resumo)
    else:
        logger.warning("=== Pipeline finalizado COM PENDÊNCIAS em %.1fs | %s ===", duracao, resumo)
    return resultados


if __name__ == "__main__":
    resultados = pipeline_principal()
    if any(status != "OK" for status in resultados.values()):
        sys.exit(1)
