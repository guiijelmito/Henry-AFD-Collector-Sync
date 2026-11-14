"""Orquestra extração e upload para os relógios V1 e V2.

A coleta é diária: cada execução envia os dias fechados (00:00 a 23:59) que a
unidade ainda não enviou, sem nunca reenviar um dia (ver ``docs/REGRAS.md``).
Cada unidade é processada mesmo que a anterior falhe. Download e upload são
repetidos algumas vezes antes de desistir. Ao final, a execução gera um
relatório (JSON e PDF), envia o alerta configurado e termina com código
diferente de zero se houver falha em qualquer relógio.
"""

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from .logging_config import SCREENSHOT_DIR, setup_logging

setup_logging()  # antes dos demais módulos do projeto emitirem logs

from . import config, relatorio  # noqa: E402
from .alertas import enviar_alerta  # noqa: E402
from .cloud import UploadSemConfirmacao, enviar_afd_para_servidor  # noqa: E402
from .extractors.henry_v1 import automatizar_download_afd_v1  # noqa: E402
from .extractors.henry_v2 import TailnetConnectionError, automatizar_download_afd_v2  # noqa: E402
from .relatorio import FALHA, FALHA_TAILSCALE, FORA_DA_JANELA  # noqa: E402
from .state_store import (  # noqa: E402
    DUVIDOSO,
    MARGEM_FECHAMENTO,
    DiaDuvidosoPendente,
    day_range,
    pending_days,
    record_doubtful_day,
    record_extra_day,
    record_scheduled_day,
    sent_status,
)

logger = logging.getLogger(__name__)

_dormir = time.sleep  # substituível nos testes


def _com_tentativas(descricao, funcao, nao_repetir=()):
    """Executa a função, repetindo após uma espera crescente se ela falhar.

    Exceções em ``nao_repetir`` sobem na hora, sem nova tentativa.
    """
    for tentativa in range(1, config.TENTATIVAS + 1):
        try:
            return funcao()
        except nao_repetir:
            raise
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


def _baixar_e_enviar(unidade, versao, dia, funcao_extracao, arquivo_estado, resultado):
    """Baixa e envia um dia. Só volta sem erro se o painel confirmou o upload."""
    data_inicial, data_final = day_range(dia)
    logger.info("[%s] Dia %s", unidade, dia.strftime("%d/%m/%Y"))

    resultado.etapa = "download"
    caminho_afd = _com_tentativas(
        f"Download {unidade}", lambda: funcao_extracao(data_inicial, data_final)
    )
    if not caminho_afd or not os.path.exists(caminho_afd):
        raise relatorio.ArquivoInvalido(f"O download da {unidade} não gerou arquivo.")

    resultado.etapa = "upload"
    try:
        _com_tentativas(
            f"Upload {unidade}",
            lambda: enviar_afd_para_servidor(caminho_afd, unidade=unidade),
            nao_repetir=(UploadSemConfirmacao,),
        )
    except UploadSemConfirmacao:
        # O arquivo pode ter chegado: trava o dia para nunca reenviá-lo sem conferência
        record_doubtful_day(arquivo_estado, versao, dia)
        resultado.dias.append(f"{dia:%d/%m/%Y}: DUVIDOSO, conferir no painel")
        raise
    resultado.dias.append(f"{dia:%d/%m/%Y}: enviado ({Path(caminho_afd).name})")


def _processar_unidade(
    unidade, etapa, funcao_extracao, agora=None, arquivo_estado=None, dias_forcados=None
):
    """Coleta e envia os dias fechados pendentes da unidade e devolve o resultado.

    Regra: um dia já enviado nunca é enviado de novo (o painel sobrescreve os
    registros). Cada dia é conferido no estado antes do download.

    Sem ``dias_forcados``, segue a fila agendada a partir de ``ultimo_dia``. Um dia
    duvidoso para a fila até ser resolvido. Com ``dias_forcados``, envia só esses
    dias, fora da fila, pulando os que já foram enviados. A exceção da unidade é
    convertida em falha para que a outra unidade também seja processada.
    """
    logger.info("[%s] Processando unidade %s", etapa, unidade)
    versao = unidade.lower()
    arquivo_estado = arquivo_estado or config.ARQUIVO_ESTADO
    agora = agora or datetime.now().astimezone()
    resultado = relatorio.ResultadoUnidade(unidade)
    inicio = time.perf_counter()
    enviados = 0
    try:
        resultado.etapa = "estado"
        forcado = dias_forcados is not None
        dias = (
            list(dias_forcados)
            if forcado
            else pending_days(arquivo_estado, versao, agora, config.MAX_DIAS_POR_EXECUCAO)
        )
        if not dias:
            logger.info("Unidade %s sem dia fechado pendente", unidade)
            resultado.status = FORA_DA_JANELA
            return resultado

        for dia in dias:
            resultado.etapa = "estado"
            motivo = sent_status(arquivo_estado, versao, dia)
            if motivo == DUVIDOSO and not forcado:
                raise DiaDuvidosoPendente(
                    f"O dia {dia:%d/%m/%Y} da unidade {unidade} teve envio duvidoso e ainda "
                    "não foi conferido no painel"
                )
            if motivo is not None:
                logger.info(
                    "Unidade %s: dia %s não será enviado (%s)", unidade, f"{dia:%d/%m/%Y}", motivo
                )
                resultado.dias.append(f"{dia:%d/%m/%Y}: não reenviado ({motivo})")
                if not forcado:
                    record_scheduled_day(arquivo_estado, versao, dia)
                continue

            _baixar_e_enviar(unidade, versao, dia, funcao_extracao, arquivo_estado, resultado)
            enviados += 1
            resultado.etapa = "estado"
            if forcado:
                record_extra_day(arquivo_estado, versao, dia)
            else:
                record_scheduled_day(arquivo_estado, versao, dia)

        if enviados == 0 and forcado:
            resultado.status = FORA_DA_JANELA
            resultado.mensagem = "Dias já enviados por esta unidade; nada foi reenviado."
            return resultado
        resultado.mensagem = f"{enviados} dia(s) baixado(s) e enviado(s) ao painel."
        logger.info(
            "Unidade %s processada em %.1fs (%d dia(s) enviado(s))",
            unidade,
            time.perf_counter() - inicio,
            enviados,
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


def executar(dias_forcados=None):
    """Processa V1 e V2 em sequência e devolve a execução com o resultado de cada uma."""
    execucao = relatorio.Execucao(inicio=datetime.now())
    coletor = relatorio.ColetorDeAvisos()
    logging.getLogger().addHandler(coletor)
    try:
        execucao.unidades = [
            _processar_unidade(
                "V1", "1/2", automatizar_download_afd_v1, dias_forcados=dias_forcados
            ),
            _processar_unidade(
                "V2", "2/2", automatizar_download_afd_v2, dias_forcados=dias_forcados
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


def dias_da_semana(dia):
    """Os 7 dias (domingo a sábado) da semana que contém ``dia``."""
    domingo = dia - timedelta(days=(dia.weekday() + 1) % 7)
    return [domingo + timedelta(days=n) for n in range(7)]


def pipeline_principal(dias=None, agora=None) -> int:
    """Executa tudo, gera o relatório, envia o alerta e devolve o código de saída.

    ``dias`` (lista de datas) força o envio desses dias fora da fila do agendamento.
    Dias ainda não fechados são ignorados, e cada unidade pula os dias que já enviou.
    """
    logger.info("=== Iniciando pipeline completo de ponto eletrônico (V1 & V2) ===")
    dias_forcados = None
    if dias is not None:
        agora = agora or datetime.now().astimezone()
        ontem = (agora - MARGEM_FECHAMENTO).date() - timedelta(days=1)
        abertos = [d for d in dias if d > ontem]
        if abertos:
            logger.warning(
                "Dias ainda não fechados ignorados: %s",
                ", ".join(f"{d:%d/%m/%Y}" for d in abertos),
            )
        dias_forcados = sorted(d for d in dias if d <= ontem)
        logger.info(
            "Dias forçados: %s (fila do agendamento não será alterada)",
            ", ".join(f"{d:%d/%m/%Y}" for d in dias_forcados) or "nenhum",
        )
    execucao = executar(dias_forcados)
    resumo = " | ".join(f"{u.unidade}={u.status}" for u in execucao.unidades)

    if not execucao.houve_coleta:
        logger.info("=== Nenhum dia pendente | %s ===", resumo)
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
