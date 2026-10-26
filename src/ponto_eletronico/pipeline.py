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
from .extractors.henry_v2 import TailnetConnectionError, automatizar_download_afd_v2  # noqa: E402
from .relatorio import FALHA, FALHA_TAILSCALE, FORA_DA_JANELA  # noqa: E402
from .state_store import audit_date_range, is_audit_due, record_audit_upload  # noqa: E402

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


def _processar_unidade(unidade, etapa, funcao_extracao, agora=None, arquivo_estado=None):
    """Executa extração e upload e devolve o resultado da unidade para o relatório.

    A exceção da unidade é registrada e convertida em falha para permitir
    que a outra unidade também seja processada.
    """
    logger.info("[%s] Processando unidade %s", etapa, unidade)
    versao = unidade.lower()
    arquivo_estado = arquivo_estado or config.ARQUIVO_ESTADO
    agora = agora or datetime.now().astimezone()
    resultado = relatorio.ResultadoUnidade(unidade)
    inicio = time.perf_counter()
    try:
        resultado.etapa = "estado"
        if not is_audit_due(arquivo_estado, versao, agora):
            logger.info(
                "Upload da unidade %s ainda não liberado (next_audit_at no futuro)", unidade
            )
            resultado.status = FORA_DA_JANELA
            return resultado

        data_inicial, data_final = audit_date_range(arquivo_estado, versao, agora)
        resultado.periodo = f"{data_inicial} a {data_final}"
        resultado.etapa = "download"
        caminho_afd = _com_tentativas(
            f"Download {unidade}", lambda: funcao_extracao(data_inicial, data_final)
        )
        if not caminho_afd or not os.path.exists(caminho_afd):
            raise relatorio.ArquivoInvalido(f"O download da {unidade} não gerou arquivo.")
        resultado.arquivo = caminho_afd

        resultado.etapa = "upload"
        _com_tentativas(
            f"Upload {unidade}", lambda: enviar_afd_para_servidor(caminho_afd, unidade=unidade)
        )
        resultado.enviado = True

        resultado.etapa = "estado"
        record_audit_upload(arquivo_estado, versao, data_final, agora)
        resultado.mensagem = "AFD do período baixado e enviado ao painel."
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
            _processar_unidade("V1", "1/2", automatizar_download_afd_v1),
            _processar_unidade("V2", "2/2", automatizar_download_afd_v2),
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
