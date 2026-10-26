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
from pathlib import Path

from .logging_config import SCREENSHOT_DIR, setup_logging

setup_logging()  # antes dos demais módulos do projeto emitirem logs

from . import config, relatorio  # noqa: E402
from .alertas import enviar_alerta  # noqa: E402
from .cloud import enviar_afd_para_servidor  # noqa: E402
from .extractors.henry_v1 import automatizar_download_afd_v1  # noqa: E402
from .extractors.henry_v2 import TailnetConnectionError, automatizar_download_afd_v2  # noqa: E402
from .relatorio import FALHA, FALHA_TAILSCALE, FORA_DA_JANELA  # noqa: E402
from .state_store import (  # noqa: E402
    is_audit_due,
    pending_weeks,
    record_week_sent,
    week_range,
    week_start,
)

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
    unidade, etapa, funcao_extracao, agora=None, arquivo_estado=None, semana_forcada=None
):
    """Coleta e envia as semanas pendentes da unidade e devolve o resultado para o relatório.

    Com ``semana_forcada`` (domingo da semana), coleta e envia só essa semana,
    sem consultar nem alterar o estado. A exceção da unidade é registrada e
    convertida em falha para permitir que a outra unidade também seja processada.
    """
    logger.info("[%s] Processando unidade %s", etapa, unidade)
    versao = unidade.lower()
    arquivo_estado = arquivo_estado or config.ARQUIVO_ESTADO
    agora = agora or datetime.now().astimezone()
    resultado = relatorio.ResultadoUnidade(unidade)
    inicio = time.perf_counter()
    try:
        resultado.etapa = "estado"
        if semana_forcada is not None:
            semanas = [semana_forcada]
        elif not is_audit_due(arquivo_estado, versao, agora):
            logger.info(
                "Coleta da unidade %s ainda não liberada (next_audit_at no futuro)", unidade
            )
            resultado.status = FORA_DA_JANELA
            return resultado
        else:
            semanas = pending_weeks(arquivo_estado, versao, agora, config.MAX_SEMANAS_POR_EXECUCAO)
        if not semanas:
            logger.info("Unidade %s sem semana encerrada pendente", unidade)
            resultado.status = FORA_DA_JANELA
            return resultado

        for semana in semanas:
            data_inicial, data_final = week_range(semana)
            periodo = f"{data_inicial} a {data_final}"
            logger.info("[%s] Semana %s", unidade, periodo)

            resultado.etapa = "download"
            caminho_afd = _com_tentativas(
                f"Download {unidade}",
                lambda inicio=data_inicial, fim=data_final: funcao_extracao(inicio, fim),
            )
            if not caminho_afd or not os.path.exists(caminho_afd):
                raise relatorio.ArquivoInvalido(f"O download da {unidade} não gerou arquivo.")

            resultado.etapa = "upload"
            _com_tentativas(
                f"Upload {unidade}",
                lambda caminho=caminho_afd: enviar_afd_para_servidor(caminho, unidade=unidade),
            )
            resultado.semanas.append(f"{periodo}: enviada ({Path(caminho_afd).name})")

            if semana_forcada is None:
                resultado.etapa = "estado"
                record_week_sent(arquivo_estado, versao, semana)

        resultado.mensagem = f"{len(semanas)} semana(s) baixada(s) e enviada(s) ao painel."
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


def executar(semana_forcada=None):
    """Processa V1 e V2 em sequência e devolve a execução com o resultado de cada uma."""
    execucao = relatorio.Execucao(inicio=datetime.now())
    coletor = relatorio.ColetorDeAvisos()
    logging.getLogger().addHandler(coletor)
    try:
        execucao.unidades = [
            _processar_unidade(
                "V1", "1/2", automatizar_download_afd_v1, semana_forcada=semana_forcada
            ),
            _processar_unidade(
                "V2", "2/2", automatizar_download_afd_v2, semana_forcada=semana_forcada
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


def pipeline_principal(semana=None) -> int:
    """Executa tudo, gera o relatório, envia o alerta e devolve o código de saída.

    ``semana`` (data dentro da semana desejada) força a coleta e o envio dessa
    semana de domingo a sábado, sem alterar o estado.
    """
    logger.info("=== Iniciando pipeline completo de ponto eletrônico (V1 & V2) ===")
    semana_forcada = None
    if semana is not None:
        semana_forcada = week_start(datetime.combine(semana, datetime.min.time()).astimezone())
        logger.info("Semana forçada: %s (estado não será alterado)", semana_forcada.date())
    execucao = executar(semana_forcada)
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
