"""Verifica a fila diária por unidade, a trava contra reenvio e a ordem upload -> estado."""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from ponto_eletronico import config, relatorio
from ponto_eletronico import pipeline as main
from ponto_eletronico.afd_validation import AFDRangeValidationError
from ponto_eletronico.cloud import UploadRecusado, UploadSemConfirmacao
from ponto_eletronico.extractors.henry_v2 import TailnetConnectionError
from ponto_eletronico.state_store import load_state_data

TZ = timezone(timedelta(hours=-3))
RUN = datetime(2026, 11, 15, 0, 5, tzinfo=TZ)  # domingo 00:05; ontem = sábado 14/11


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(config, "TENTATIVAS", 3)
    monkeypatch.setattr(main, "_dormir", lambda segundos: None)


@pytest.fixture
def estado(tmp_path):
    return tmp_path / "estado_ponto.json"


@pytest.fixture
def afd(tmp_path):
    caminho = tmp_path / "sample.afd"
    caminho.write_text("record", encoding="utf-8")
    return str(caminho)


def processar(unidade, extrator, estado, agora=RUN, dias_forcados=None):
    return main._processar_unidade(unidade, "1/1", extrator, agora, estado, dias_forcados)


def nao_chamar(*args, **kwargs):
    raise AssertionError("dia já enviado não pode ser baixado nem enviado de novo")


def test_sends_yesterday_and_records_state_only_after_upload(estado, afd, monkeypatch):
    eventos = []
    monkeypatch.setattr(
        main,
        "enviar_afd_para_servidor",
        lambda path, unidade: eventos.append(load_state_data(estado)),
    )

    def extrator(inicio, fim):
        eventos.append((inicio, fim))
        return afd

    resultado = processar("V1", extrator, estado)

    assert resultado.status == "OK"
    assert eventos == [("14/11/2026 00:00", "14/11/2026 23:59"), {}]  # estado vazio no upload
    assert resultado.dias == ["14/11/2026: enviado (sample.afd)"]
    assert load_state_data(estado) == {"ultimo_dia_v1": "2026-11-14"}


def test_up_to_date_unit_does_nothing(estado):
    estado.write_text('{"ultimo_dia_v1": "2026-11-14"}', encoding="utf-8")
    assert processar("V1", nao_chamar, estado).status == "FORA_DA_JANELA"


def test_late_run_sends_each_missed_day_in_order(estado, afd, monkeypatch):
    estado.write_text('{"ultimo_dia_v1": "2026-11-11"}', encoding="utf-8")
    monkeypatch.setattr(main, "enviar_afd_para_servidor", lambda path, unidade: None)
    periodos = []

    def extrator(inicio, fim):
        periodos.append(inicio)
        return afd

    resultado = processar("V1", extrator, estado)

    assert periodos == ["12/11/2026 00:00", "13/11/2026 00:00", "14/11/2026 00:00"]
    assert resultado.mensagem.startswith("3 dia(s)")
    assert load_state_data(estado)["ultimo_dia_v1"] == "2026-11-14"


def test_recovery_is_per_unit(estado, afd, monkeypatch):
    estado.write_text(
        '{"ultimo_dia_v1": "2026-11-14", "ultimo_dia_v2": "2026-11-12"}', encoding="utf-8"
    )
    monkeypatch.setattr(main, "enviar_afd_para_servidor", lambda path, unidade: None)
    periodos = []

    def extrator(inicio, fim):
        periodos.append(inicio)
        return afd

    assert processar("V1", nao_chamar, estado).status == "FORA_DA_JANELA"
    assert processar("V2", extrator, estado).status == "OK"
    assert periodos == ["13/11/2026 00:00", "14/11/2026 00:00"]
    assert load_state_data(estado) == {"ultimo_dia_v1": "2026-11-14", "ultimo_dia_v2": "2026-11-14"}


def test_recovery_skips_days_already_sent_outside_the_queue(estado, afd, monkeypatch):
    estado.write_text(
        '{"ultimo_dia_v1": "2026-11-11", "dias_avulsos_v1": ["2026-11-13"]}', encoding="utf-8"
    )
    monkeypatch.setattr(main, "enviar_afd_para_servidor", lambda path, unidade: None)
    periodos = []

    def extrator(inicio, fim):
        periodos.append(inicio)
        return afd

    resultado = processar("V1", extrator, estado)

    assert periodos == ["12/11/2026 00:00", "14/11/2026 00:00"]
    assert "13/11/2026: não reenviado" in resultado.dias[1]
    assert load_state_data(estado)["ultimo_dia_v1"] == "2026-11-14"


def test_old_weekly_state_never_resends_the_last_weekly_upload(estado, afd, monkeypatch):
    estado.write_text(
        '{"ultima_semana_v1": "2026-11-01", "semanas_avulsas_v1": ["2026-11-08"]}',
        encoding="utf-8",
    )
    enviados = []
    monkeypatch.setattr(main, "enviar_afd_para_servidor", lambda path, unidade: enviados.append(1))

    resultado = processar("V1", nao_chamar, estado)

    # 08/11 a 14/11 foram enviados com --semana na coleta antiga: nada é reenviado
    assert resultado.status == "OK"
    assert enviados == []
    assert load_state_data(estado)["ultimo_dia_v1"] == "2026-11-14"


def test_failure_in_second_day_keeps_the_first_one_recorded(estado, afd, monkeypatch):
    estado.write_text('{"ultimo_dia_v1": "2026-11-12"}', encoding="utf-8")
    enviados = []

    def upload(path, unidade):
        if enviados:
            raise RuntimeError("upload failed")
        enviados.append(path)

    monkeypatch.setattr(main, "enviar_afd_para_servidor", upload)

    resultado = processar("V1", lambda inicio, fim: afd, estado)

    assert resultado.status == "FALHA"
    assert load_state_data(estado)["ultimo_dia_v1"] == "2026-11-13"


def test_state_is_not_recorded_when_upload_is_refused(estado, afd, monkeypatch):
    tentativas = []

    def recusado(path, unidade):
        tentativas.append(1)
        raise UploadRecusado("HTTP 401")

    monkeypatch.setattr(main, "enviar_afd_para_servidor", recusado)

    resultado = processar("V1", lambda inicio, fim: afd, estado)

    assert resultado.status == "FALHA"
    assert len(tentativas) == 3  # recusado = nada gravado, tentar de novo é seguro
    assert "recusou" in resultado.mensagem
    assert load_state_data(estado) == {}


def test_upload_without_confirmation_is_not_retried_and_locks_the_day(estado, afd, monkeypatch):
    tentativas = []

    def sem_resposta(path, unidade):
        tentativas.append(1)
        raise UploadSemConfirmacao("sem resposta")

    monkeypatch.setattr(main, "enviar_afd_para_servidor", sem_resposta)

    resultado = processar("V1", lambda inicio, fim: afd, estado)

    assert resultado.status == "FALHA"
    assert len(tentativas) == 1
    assert "NÃO será reenviado" in resultado.mensagem
    assert "--resolver-duvidoso" in resultado.o_que_fazer
    assert load_state_data(estado) == {"dias_duvidosos_v1": ["2026-11-14"]}


def test_queue_stops_at_a_doubtful_day_until_it_is_resolved(estado, monkeypatch):
    estado.write_text(
        '{"ultimo_dia_v1": "2026-11-12", "dias_duvidosos_v1": ["2026-11-13"]}', encoding="utf-8"
    )
    original = estado.read_text(encoding="utf-8")
    monkeypatch.setattr(main, "enviar_afd_para_servidor", nao_chamar)

    resultado = processar("V1", nao_chamar, estado)

    assert resultado.status == "FALHA"
    assert "parada" in resultado.mensagem
    assert estado.read_text(encoding="utf-8") == original


def test_forced_days_are_recorded_without_touching_the_queue(estado, afd, monkeypatch):
    estado.write_text('{"ultimo_dia_v1": "2026-11-05"}', encoding="utf-8")
    monkeypatch.setattr(main, "enviar_afd_para_servidor", lambda path, unidade: None)
    periodos = []

    def extrator(inicio, fim):
        periodos.append((inicio, fim))
        return afd

    resultado = processar("V1", extrator, estado, dias_forcados=[date(2026, 11, 10)])

    assert resultado.status == "OK"
    assert periodos == [("10/11/2026 00:00", "10/11/2026 23:59")]
    assert load_state_data(estado) == {
        "ultimo_dia_v1": "2026-11-05",
        "dias_avulsos_v1": ["2026-11-10"],
    }


@pytest.mark.parametrize(
    "estado_inicial",
    [
        '{"dias_avulsos_v2": ["2026-11-10"]}',
        '{"ultimo_dia_v2": "2026-11-10"}',
        '{"semanas_avulsas_v2": ["2026-11-08"]}',
        '{"ultima_semana_v2": "2026-11-08"}',
        '{"dias_duvidosos_v2": ["2026-11-10"]}',
    ],
)
def test_forced_rerun_never_resends_a_day(estado, estado_inicial, monkeypatch):
    estado.write_text(estado_inicial, encoding="utf-8")
    monkeypatch.setattr(main, "enviar_afd_para_servidor", nao_chamar)

    resultado = processar("V2", nao_chamar, estado, dias_forcados=[date(2026, 11, 10)])

    assert resultado.status == "FORA_DA_JANELA"
    assert "nada foi reenviado" in resultado.mensagem
    assert estado.read_text(encoding="utf-8") == estado_inicial


def test_forced_week_sends_only_the_days_not_yet_sent(estado, afd, monkeypatch):
    estado.write_text('{"dias_avulsos_v1": ["2026-11-09", "2026-11-10"]}', encoding="utf-8")
    monkeypatch.setattr(main, "enviar_afd_para_servidor", lambda path, unidade: None)
    periodos = []

    def extrator(inicio, fim):
        periodos.append(inicio[:5])
        return afd

    dias = main.dias_da_semana(date(2026, 11, 12))
    resultado = processar("V1", extrator, estado, dias_forcados=dias)

    assert resultado.status == "OK"
    assert periodos == ["08/11", "11/11", "12/11", "13/11", "14/11"]


def test_forced_day_failed_upload_is_not_recorded(estado, afd, monkeypatch):
    def failed_upload(path, unidade):
        raise RuntimeError("upload failed")

    monkeypatch.setattr(main, "enviar_afd_para_servidor", failed_upload)

    resultado = processar("V1", lambda inicio, fim: afd, estado, dias_forcados=[date(2026, 11, 10)])

    assert resultado.status == "FALHA"
    assert load_state_data(estado) == {}


def test_tailnet_connection_failure_has_specific_status_and_message(estado, caplog):
    def connection_failure(inicio, fim):
        raise TailnetConnectionError("Não foi possível alcançar o painel V2")

    resultado = processar("V2", connection_failure, estado)

    assert resultado.status == "FALHA_TAILSCALE"
    assert "Tailscale" in resultado.o_que_fazer
    assert "Falha de conexão Tailscale" in caplog.text


def test_temporary_download_failure_is_retried(estado, afd, monkeypatch):
    monkeypatch.setattr(main, "enviar_afd_para_servidor", lambda path, unidade: None)
    attempts = []

    def unstable_download(inicio, fim):
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("net::ERR_CONNECTION_TIMED_OUT")
        return afd

    assert processar("V1", unstable_download, estado).status == "OK"
    assert len(attempts) == 3


def test_afd_fora_do_intervalo_nao_e_baixado_de_novo(estado, monkeypatch):
    monkeypatch.setattr(main, "enviar_afd_para_servidor", nao_chamar)
    attempts = []

    def download_invalido(inicio, fim):
        attempts.append(1)
        raise AFDRangeValidationError("1 marcação(ões) fora do intervalo solicitado")

    resultado = processar("V1", download_invalido, estado)

    assert resultado.status != "OK"
    assert len(attempts) == 1


def test_upload_failure_after_all_attempts_explains_what_to_do(estado, afd, monkeypatch):
    attempts = []

    def failed_upload(path, unidade):
        attempts.append(1)
        raise RuntimeError("Timeout 15000ms exceeded")

    monkeypatch.setattr(main, "enviar_afd_para_servidor", failed_upload)

    resultado = processar("V1", lambda inicio, fim: afd, estado)

    assert resultado.status == "FALHA"
    assert resultado.etapa == "upload"
    assert "painel" in resultado.mensagem
    assert len(attempts) == 3


def _fake_execucao(status):
    return relatorio.Execucao(
        inicio=datetime(2026, 10, 30), unidades=[relatorio.ResultadoUnidade("V1", status)]
    )


def test_failure_exits_with_1_and_writes_json_and_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(relatorio, "RELATORIOS_DIR", tmp_path)
    monkeypatch.setattr(main, "executar", lambda dias_forcados=None: _fake_execucao("FALHA"))
    monkeypatch.setattr(main, "enviar_alerta", lambda execucao, pdf: None)

    assert main.pipeline_principal() == 1

    [arquivo_json] = tmp_path.glob("*.json")
    assert json.loads(arquivo_json.read_text("utf-8"))["status_geral"] == "FALHA"
    [pdf] = tmp_path.glob("*.pdf")
    assert pdf.read_bytes().startswith(b"%PDF")


def test_closed_window_exits_0_without_report_or_alert(tmp_path, monkeypatch):
    monkeypatch.setattr(relatorio, "RELATORIOS_DIR", tmp_path)
    monkeypatch.setattr(
        main, "executar", lambda dias_forcados=None: _fake_execucao("FORA_DA_JANELA")
    )
    monkeypatch.setattr(main, "enviar_alerta", lambda execucao, pdf: pytest.fail("no alert"))

    assert main.pipeline_principal() == 0
    assert not list(tmp_path.iterdir())


def test_week_option_becomes_sunday_to_saturday():
    dias = main.dias_da_semana(date(2026, 11, 12))
    assert dias[0] == date(2026, 11, 8)
    assert dias[-1] == date(2026, 11, 14)
    assert len(dias) == 7


def test_forced_days_not_closed_yet_are_ignored(monkeypatch):
    recebido = []
    monkeypatch.setattr(
        main,
        "executar",
        lambda dias_forcados=None: (
            recebido.append(dias_forcados) or _fake_execucao("FORA_DA_JANELA")
        ),
    )

    main.pipeline_principal(dias=[date(2026, 11, 15), date(2026, 11, 13)], agora=RUN)

    assert recebido == [[date(2026, 11, 13)]]


def test_days_already_sent_do_not_use_the_per_run_limit(estado, afd, monkeypatch):
    # Caso real de 18/11: 08 a 14/11 já enviados à mão; o limite de 7 não pode parar a fila
    estado.write_text(
        json.dumps(
            {
                "ultimo_dia_v1": "2026-11-07",
                "dias_avulsos_v1": [f"2026-11-{d:02d}" for d in range(8, 15)],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "MAX_DIAS_POR_EXECUCAO", 7)
    monkeypatch.setattr(main, "enviar_afd_para_servidor", lambda path, unidade: None)
    periodos = []

    def extrator(inicio, fim):
        periodos.append(inicio[:5])
        return afd

    agora = datetime(2026, 11, 18, 8, 30, tzinfo=TZ)
    resultado = processar("V1", extrator, estado, agora=agora)

    assert periodos == ["15/11", "16/11", "17/11"]
    assert load_state_data(estado)["ultimo_dia_v1"] == "2026-11-17"
    assert resultado.mensagem.startswith("3 dia(s)")


def test_per_run_limit_counts_only_days_sent(estado, afd, monkeypatch):
    estado.write_text('{"ultimo_dia_v1": "2026-11-09"}', encoding="utf-8")
    monkeypatch.setattr(config, "MAX_DIAS_POR_EXECUCAO", 2)
    monkeypatch.setattr(main, "enviar_afd_para_servidor", lambda path, unidade: None)

    resultado = processar("V1", lambda inicio, fim: afd, estado)

    assert resultado.mensagem.startswith("2 dia(s)")
    assert load_state_data(estado)["ultimo_dia_v1"] == "2026-11-11"
