"""Orquestra extração e upload para os relógios V1 e V2.

Cada unidade é processada mesmo que a anterior falhe. Download e upload são
repetidos algumas vezes antes de desistir. Ao final, a execução gera um
relatório (JSON e PDF), envia o alerta configurado e termina com código
diferente de zero se houver falha em qualquer relógio.
"""

import logging
import os
import time
from datetime import datetime

from .logging_config import SCREENSHOT_DIR, setup_logging

setup_logging()  # antes dos demais módulos do projeto emitirem logs

from . import config, relatorio  # noqa: E402
from .alertas import enviar_alerta  # noqa: E402
from .cloud import enviar_afd_para_servidor  # noqa: E402
from .extractors.henry_v1 import automatizar_download_afd_v1  # noqa: E402
from .extractors.henry_v1 import janela_semanal_vencida as janela_v1_vencida  # noqa: E402
from .extractors.henry_v1 import registrar_upload_enviado as registrar_upload_v1  # noqa: E402
from .extractors.henry_v2 import TailnetConnectionError, automatizar_download_afd_v2  # noqa: E402
from .extractors.henry_v2 import janela_semanal_vencida as janela_v2_vencida  # noqa: E402
from .extractors.henry_v2 import registrar_upload_enviado as registrar_upload_v2  # noqa: E402
from .relatorio import FALHA, FALHA_TAILSCALE, FORA_DA_JANELA  # noqa: E402

logger = logging.getLogger(__name__)

_dormir = time.sleep  # substituível nos testes


def _com_tentativas(descricao, funcao):
    """Executa a função, repetindo após uma espera crescente se ela falhar."""
    for tentativa in range(1, config.TENTATIVAS + 1):
        try:
            return funcao()
        except Exception:
            if tentativa == config.TENTATIVAS:
                raise
            espera = config.ESPERA_ENTRE_TENTATIVAS_S * tentativa
            logger.warning(
                "%s falhou (tentativa %d de %d); nova tentativa em %ds",
                descricao,
                tentativa,
                config.TENTATIVAS,
                espera,
                exc_info=True,
            )
            _dormir(espera)


def _processar_unidade(
    unidade,
    etapa,
    janela_vencida,
    funcao_extracao,
    registrar_upload,
):
    """Executa extração e upload e devolve o resultado da unidade para o relatório.

    A exceção da unidade é registrada e convertida em falha para permitir
    que a outra unidade também seja processada.
    """
    logger.info("[%s] Processando unidade %s", etapa, unidade)
    resultado = relatorio.ResultadoUnidade(unidade)
    inicio = time.perf_counter()
    try:
        if not janela_vencida():
            logger.info(
                "Janela semanal da unidade %s ainda não venceu; extração e upload adiados",
                unidade,
            )
            resultado.status = FORA_DA_JANELA
            return resultado

        resultado.etapa = "download"
        caminho_afd = _com_tentativas(f"Download {unidade}", funcao_extracao)
        if not caminho_afd or not os.path.exists(caminho_afd):
            raise relatorio.ArquivoInvalido(f"O download da {unidade} não gerou arquivo.")
        resultado.arquivo = caminho_afd

        resultado.etapa = "upload"
        _com_tentativas(
            f"Upload {unidade}", lambda: enviar_afd_para_servidor(caminho_afd, unidade=unidade)
        )
        resultado.enviado = True

        resultado.etapa = "agendamento"
        registrar_upload()
        resultado.mensagem = "AFD da semana baixado e enviado ao painel."
        logger.info(
            "Unidade %s processada e enviada com sucesso em %.1fs",
            unidade,
            time.perf_counter() - inicio,
        )
    except TailnetConnectionError as exc:
        logger.error("Falha de conexão Tailscale com a unidade %s: %s", unidade, exc)
        _registrar_falha(resultado, FALHA_TAILSCALE, exc)
    except Exception as exc:
        logger.exception("Falha crítica no pipeline da unidade %s", unidade)
        _registrar_falha(resultado, FALHA, exc)
    finally:
        resultado.duracao_s = time.perf_counter() - inicio
    return resultado


def _registrar_falha(resultado, status, exc):
    resultado.status = status
    resultado.erro_tecnico = f"{type(exc).__name__}: {exc}"
    resultado.mensagem, resultado.o_que_fazer = relatorio.interpretar_erro(
        exc, resultado.etapa, resultado.unidade
    )


def executar():
    """Processa V1 e V2 em sequência e devolve a execução com o resultado de cada uma."""
    execucao = relatorio.Execucao(inicio=datetime.now())
    coletor = relatorio.ColetorDeAvisos()
    logging.getLogger().addHandler(coletor)
    try:
        execucao.unidades = [
            _processar_unidade(
                "V1", "1/2", janela_v1_vencida, automatizar_download_afd_v1, registrar_upload_v1
            ),
            _processar_unidade(
                "V2", "2/2", janela_v2_vencida, automatizar_download_afd_v2, registrar_upload_v2
            ),
        ]
    finally:
        logging.getLogger().removeHandler(coletor)
    execucao.fim = datetime.now()
    execucao.avisos = coletor.linhas
    if SCREENSHOT_DIR.exists():
        execucao.screenshots = sorted(
            str(p)
            for p in SCREENSHOT_DIR.glob("*.png")
            if p.stat().st_mtime >= execucao.inicio.timestamp()
        )
    return execucao


def pipeline_principal() -> int:
    """Executa tudo, gera o relatório, envia o alerta e devolve o código de saída."""
    logger.info("=== Iniciando pipeline completo de ponto eletrônico (V1 & V2) ===")
    execucao = executar()
    resumo = " | ".join(f"{u.unidade}={u.status}" for u in execucao.unidades)

    if not execucao.houve_coleta:
        logger.info("=== Nenhuma unidade na janela de coleta | %s ===", resumo)
        return 0

    pdf = None
    try:
        logger.info("Relatório JSON: %s", relatorio.salvar_json(execucao))
        pdf = relatorio.gerar_pdf(execucao)
        logger.info("Relatório PDF: %s", pdf)
    except Exception:
        logger.exception("Não foi possível gerar o relatório da execução")

    enviar_alerta(execucao, pdf)

    if execucao.houve_falha:
        logger.warning("=== Pipeline finalizado COM PENDÊNCIAS | %s ===", resumo)
        return 1
    logger.info("=== Pipeline finalizado | %s ===", resumo)
    return 0


if __name__ == "__main__":
    raise SystemExit(pipeline_principal())
