import json
from datetime import date

import pytest

from ponto_eletronico import config, estado, pipeline, relatorio
from ponto_eletronico.afd import analisar_afd

SEXTA = date(2026, 10, 30)


def escrever_afd(caminho, nsrs):
    linhas = ["0000000001" + "X" * 20]
    linhas += [f"{n:09d}3301020261200{n:012d}" for n in nsrs]
    linhas.append("9999999999")
    caminho.write_text("\n".join(linhas) + "\n", encoding="latin-1")
    return str(caminho)


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(estado, "ARQUIVO_ESTADO", tmp_path / "estado_ponto.json")
    monkeypatch.setattr(config, "LOTE_NSR", 10)
    monkeypatch.setattr(config, "MAX_LOTES_POR_EXECUCAO", 5)
    monkeypatch.setattr(config, "TENTATIVAS", 3)
    monkeypatch.setattr(pipeline, "_dormir", lambda s: None)
    return tmp_path


def relogio(tmp_path, ultimo_existente, unidade="V1"):
    """Simula o relógio: devolve os NSRs do intervalo que já existem."""

    def extrator(inicial, final):
        nsrs = range(inicial, min(final, ultimo_existente) + 1)
        return escrever_afd(tmp_path / f"{unidade}_{inicial}.txt", nsrs)

    return extrator


def test_analisar_afd(tmp_path):
    resumo = analisar_afd(escrever_afd(tmp_path / "a.txt", [100, 101, 105]))
    assert resumo.reconhecido
    assert resumo.ultimo_nsr == 105
    assert resumo.novos_apos(100) == 2


def test_coleta_envia_e_so_entao_avanca_nsr_e_janela(ambiente):
    estado.salvar({"last_nsr_v1": "000000100", "next_date": "2026-10-30"})
    enviados = []

    execucao = pipeline.executar(
        hoje=SEXTA,
        extratores={"V1": relogio(ambiente, 104)},
        enviar=lambda arq, unidade: enviados.append(arq),
    )

    [v1] = execucao.unidades
    assert v1.status == relatorio.OK
    assert len(enviados) == 1
    dados = estado.carregar()
    assert dados["last_nsr_v1"] == "000000104"  # último NSR realmente baixado
    assert dados["next_date_v1"] == "2026-11-06"


def test_fora_da_janela_nao_baixa_nada(ambiente):
    estado.salvar({"next_date": "2026-11-06"})
    chamado = []
    execucao = pipeline.executar(
        hoje=SEXTA, extratores={"V1": lambda i, f: chamado.append(1)}, enviar=None
    )
    assert execucao.unidades[0].status == relatorio.AGUARDANDO
    assert not chamado
    assert execucao.status_geral == "AGUARDANDO"


def test_forcar_ignora_a_janela(ambiente):
    estado.salvar({"last_nsr_v1": "000000100", "next_date": "2026-11-06"})
    execucao = pipeline.executar(
        forcar=True,
        hoje=SEXTA,
        extratores={"V1": relogio(ambiente, 103)},
        enviar=lambda a, unidade: None,
    )
    assert execucao.unidades[0].status == relatorio.OK


def test_lote_cheio_busca_o_proximo_lote_na_mesma_execucao(ambiente):
    estado.salvar({"last_nsr_v1": "000000100"})
    enviados = []
    execucao = pipeline.executar(
        hoje=SEXTA,
        extratores={"V1": relogio(ambiente, 125)},
        enviar=lambda arq, unidade: enviados.append(arq),
    )
    assert execucao.unidades[0].status == relatorio.OK
    assert len(enviados) == 3  # 100-110, 110-120, 120-125
    assert estado.carregar()["last_nsr_v1"] == "000000125"


def test_falha_no_upload_nao_avanca_o_nsr(ambiente):
    estado.salvar({"last_nsr_v1": "000000100", "next_date": "2026-10-30"})

    def upload_quebrado(arq, unidade):
        raise RuntimeError("Timeout 15000ms exceeded")

    execucao = pipeline.executar(
        hoje=SEXTA, extratores={"V1": relogio(ambiente, 104)}, enviar=upload_quebrado
    )
    [v1] = execucao.unidades
    assert v1.status == relatorio.FALHA
    assert v1.etapa == "upload"
    assert "painel" in v1.mensagem
    dados = estado.carregar()
    assert dados["last_nsr_v1"] == "000000100"
    assert "next_date_v1" not in dados


def test_tentativas_recuperam_falha_temporaria(ambiente):
    estado.salvar({"last_nsr_v2": "000000100"})
    chamadas = []
    real = relogio(ambiente, 102, "V2")

    def instavel(inicial, final):
        chamadas.append(1)
        if len(chamadas) < 3:
            raise RuntimeError("net::ERR_CONNECTION_TIMED_OUT")
        return real(inicial, final)

    execucao = pipeline.executar(
        hoje=SEXTA, extratores={"V2": instavel}, enviar=lambda a, unidade: None
    )
    assert execucao.unidades[0].status == relatorio.OK
    assert len(chamadas) == 3


def test_relogio_fora_do_ar_explica_o_que_fazer(ambiente):
    def fora(inicial, final):
        raise RuntimeError("net::ERR_CONNECTION_TIMED_OUT at http://100.64.0.1")

    execucao = pipeline.executar(hoje=SEXTA, extratores={"V2": fora}, enviar=None)
    [v2] = execucao.unidades
    assert v2.status == relatorio.FALHA
    assert "Tailscale" in v2.o_que_fazer
    assert execucao.status_geral == "FALHA"


def test_sem_registros_novos_nao_envia(ambiente):
    estado.salvar({"last_nsr_v1": "000000100"})
    enviados = []
    execucao = pipeline.executar(
        hoje=SEXTA,
        extratores={"V1": relogio(ambiente, 100)},
        enviar=lambda arq, unidade: enviados.append(arq),
    )
    assert execucao.unidades[0].status == relatorio.SEM_NOVIDADES
    assert not enviados
    assert estado.carregar()["next_date_v1"] == "2026-11-06"


def test_estado_corrompido_vira_falha_explicada(ambiente):
    estado.ARQUIVO_ESTADO.write_text("{quebrado", encoding="utf-8")
    execucao = pipeline.executar(hoje=SEXTA, extratores={"V1": None}, enviar=None)
    assert execucao.unidades[0].status == relatorio.FALHA
    assert "estado_ponto.json" in execucao.unidades[0].mensagem


def test_pipeline_principal_retorna_1_em_falha_e_gera_relatorios(ambiente, monkeypatch):
    monkeypatch.setattr(relatorio, "RELATORIOS_DIR", ambiente / "relatorios")
    monkeypatch.setattr(pipeline, "enviar_alerta", lambda execucao, pdf: None)

    def fora(inicial, final):
        raise RuntimeError("net::ERR_CONNECTION_REFUSED")

    monkeypatch.setattr(pipeline, "EXTRATORES", {"V1": fora})
    assert pipeline.pipeline_principal() == 1

    [arquivo_json] = (ambiente / "relatorios").glob("*.json")
    assert json.loads(arquivo_json.read_text("utf-8"))["status_geral"] == "FALHA"
    [pdf] = (ambiente / "relatorios").glob("*.pdf")
    assert pdf.read_bytes().startswith(b"%PDF")
