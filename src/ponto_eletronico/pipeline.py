import logging
import os
import time
from datetime import date, datetime

from .logging_config import SCREENSHOT_DIR, setup_logging

setup_logging()  # antes dos demais módulos do projeto emitirem logs

from . import config, estado, relatorio  # noqa: E402
from .afd import analisar_afd  # noqa: E402
from .alertas import enviar_alerta  # noqa: E402
from .cloud import enviar_afd_para_servidor  # noqa: E402
from .extractors.henry_v1 import automatizar_download_afd_v1  # noqa: E402
from .extractors.henry_v2 import automatizar_download_afd_v2  # noqa: E402
from .relatorio import AGUARDANDO, FALHA, OK, SEM_NOVIDADES, ArquivoInvalido  # noqa: E402

logger = logging.getLogger(__name__)

EXTRATORES = {"V1": automatizar_download_afd_v1, "V2": automatizar_download_afd_v2}
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


def _coletar_unidade(unidade, extrator, enviar, forcar, hoje):
    resultado = relatorio.ResultadoUnidade(unidade)
    inicio = time.perf_counter()
    resultado.etapa = "estado"
    try:
        dados = estado.carregar()
        if not forcar and not estado.coleta_liberada(dados, unidade, hoje):
            proxima = estado.proxima_coleta(dados, unidade)
            resultado.status = AGUARDANDO
            resultado.proxima_coleta = f"{proxima:%d/%m/%Y}"
            resultado.mensagem = f"Próxima coleta liberada a partir de {proxima:%d/%m/%Y}."
            logger.info("[%s] Fora da janela de coleta; %s", unidade, resultado.mensagem)
            return resultado

        lote_cheio = False
        for _ in range(config.MAX_LOTES_POR_EXECUCAO):
            lote_cheio = False
            nsr_inicial = estado.ultimo_nsr(dados, unidade)
            lote = relatorio.Lote(nsr_inicial, nsr_inicial + config.LOTE_NSR)
            resultado.lotes.append(lote)

            resultado.etapa = "download"
            lote.arquivo = _com_tentativas(
                f"Download {unidade}", lambda lote=lote: extrator(lote.nsr_inicial, lote.nsr_final)
            )
            if not lote.arquivo or not os.path.exists(lote.arquivo):
                raise ArquivoInvalido(f"O download da {unidade} não gerou arquivo.")
            if os.path.getsize(lote.arquivo) == 0:
                raise ArquivoInvalido(f"O arquivo baixado da {unidade} está vazio (0 bytes).")

            resumo = analisar_afd(lote.arquivo)
            if resumo.reconhecido:
                lote.registros_novos = resumo.novos_apos(nsr_inicial)
                lote.ultimo_nsr = resumo.ultimo_nsr
                if lote.registros_novos == 0:
                    logger.info("[%s] Nenhum registro novo após o NSR %09d", unidade, nsr_inicial)
                    break
            else:
                # Formato não reconhecido: mantém o comportamento antigo (assume o lote inteiro)
                logger.warning(
                    "[%s] Formato do AFD não reconhecido; assumindo NSR final %09d",
                    unidade,
                    lote.nsr_final,
                )
                lote.ultimo_nsr = lote.nsr_final

            resultado.etapa = "upload"
            _com_tentativas(
                f"Upload {unidade}",
                lambda lote=lote: enviar(lote.arquivo, unidade=unidade),
            )
            lote.enviado = True

            # O NSR só avança depois do upload, e só até o último registro realmente baixado
            resultado.etapa = "estado"
            estado.registrar_nsr(dados, unidade, max(nsr_inicial, lote.ultimo_nsr))
            estado.salvar(dados)

            lote_cheio = resumo.reconhecido and lote.ultimo_nsr >= lote.nsr_final
            if not lote_cheio:
                break
            logger.info("[%s] Lote cheio; buscando o próximo intervalo de NSR", unidade)

        novos = sum(lote.registros_novos for lote in resultado.lotes)
        enviados = sum(1 for lote in resultado.lotes if lote.enviado)
        if lote_cheio:
            # Ainda há registros: não fecha a janela, a próxima execução continua de onde parou
            resultado.mensagem = (
                f"{novos} registro(s) enviados em {enviados} lote(s). Ainda há registros; "
                "a próxima execução continua a coleta."
            )
        else:
            proxima = estado.avancar_janela(dados, unidade, hoje)
            estado.salvar(dados)
            resultado.proxima_coleta = f"{proxima:%d/%m/%Y}"
            resultado.mensagem = f"{novos} registro(s) novo(s) enviados em {enviados} lote(s)."
        resultado.status = OK if enviados else SEM_NOVIDADES
        if not enviados:
            resultado.mensagem = "Nenhuma batida nova desde a última coleta."

    except Exception as exc:
        logger.exception("[%s] Falha na etapa '%s'", unidade, resultado.etapa)
        resultado.status = FALHA
        resultado.erro_tecnico = f"{type(exc).__name__}: {exc}"
        resultado.mensagem, resultado.o_que_fazer = relatorio.interpretar_erro(
            exc, resultado.etapa, unidade
        )
    finally:
        resultado.duracao_s = time.perf_counter() - inicio
    return resultado


def executar(forcar=False, hoje=None, extratores=None, enviar=enviar_afd_para_servidor):
    """Roda a coleta de todas as unidades e devolve a Execucao (sem relatório/alerta)."""
    hoje = hoje or date.today()
    execucao = relatorio.Execucao(inicio=datetime.now())
    coletor = relatorio.ColetorDeAvisos()
    logging.getLogger().addHandler(coletor)
    try:
        for unidade, extrator in (extratores or EXTRATORES).items():
            logger.info("Processando unidade %s", unidade)
            execucao.unidades.append(_coletar_unidade(unidade, extrator, enviar, forcar, hoje))
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


def pipeline_principal(forcar=False):
    """Executa tudo, gera o relatório, envia o alerta e devolve o código de saída."""
    logger.info("=== Iniciando pipeline de ponto eletrônico (forcar=%s) ===", forcar)
    execucao = executar(forcar=forcar)
    if not execucao.houve_coleta:
        logger.info("=== Nenhuma unidade na janela de coleta; nada a fazer ===")
        return 0

    pdf = None
    try:
        logger.info("Relatório JSON: %s", relatorio.salvar_json(execucao))
        pdf = relatorio.gerar_pdf(execucao)
        logger.info("Relatório PDF: %s", pdf)
    except Exception:
        logger.exception("Não foi possível gerar o relatório da execução")

    enviar_alerta(execucao, pdf)

    resumo = " | ".join(f"{u.unidade}={u.status}" for u in execucao.unidades)
    if execucao.houve_falha:
        logger.error("=== Pipeline finalizado COM FALHA | %s ===", resumo)
        return 1
    logger.info("=== Pipeline finalizado | %s ===", resumo)
    return 0


if __name__ == "__main__":
    raise SystemExit(pipeline_principal())
