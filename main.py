import logging
import os
import time

from logging_config import setup_logging

setup_logging()  # antes dos demais módulos do projeto emitirem logs

from extract_afc_v1 import automatizar_download_afd_v1  # noqa: E402
from extract_afc_v2 import automatizar_download_afd_v2  # noqa: E402
from cloud import enviar_afd_para_servidor  # noqa: E402

logger = logging.getLogger(__name__)


def _processar_unidade(unidade, etapa, funcao_extracao, dica_falha=""):
    """Executa extração + upload de uma unidade e retorna o status ('OK', 'SEM_ARQUIVO' ou 'FALHA')."""
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


def pipeline_principal():
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


if __name__ == "__main__":
    pipeline_principal()
