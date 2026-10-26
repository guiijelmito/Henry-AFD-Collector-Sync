"""Verifica a liberação pelo next_date, as semanas coletadas e a ordem upload -> estado."""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from ponto_eletronico import config, relatorio
from ponto_eletronico import pipeline as main
from ponto_eletronico.extractors.henry_v2 import TailnetConnectionError
from ponto_eletronico.state_store import load_state_data

SUNDAY = datetime(2026, 10, 25, 0, 5, tzinfo=timezone(timedelta(hours=-3)))


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


def processar(unidade, extrator, estado, agora=SUNDAY, semana_forcada=None):
    return main._processar_unidade(unidade, "1/1", extrator, agora, estado, semana_forcada)


def test_collects_closed_week_then_records_state_after_upload(estado, afd, monkeypatch):
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
    assert eventos == [("18/10/2026 00:00", "24/10/2026 23:59"), {}]  # estado vazio no upload
    assert resultado.semanas == ["18/10/2026 00:00 a 24/10/2026 23:59: enviada (sample.afd)"]
    assert load_state_data(estado) == {
        "ultima_semana_v1": "2026-10-18",
        "next_audit_at_v1": "2026-11-01T00:05-03:00",
    }


def test_late_run_sends_each_missed_week_in_order(estado, afd, monkeypatch):
    estado.write_text('{"ultima_semana_v1": "2026-10-04"}', encoding="utf-8")
    monkeypatch.setattr(main, "enviar_afd_para_servidor", lambda path, unidade: None)
    periodos = []

    def extrator(inicio, fim):
        periodos.append(inicio)
        return afd

    resultado = processar("V1", extrator, estado)

    assert periodos == ["11/10/2026 00:00", "18/10/2026 00:00"]
    assert len(resultado.semanas) == 2
    assert load_state_data(estado)["ultima_semana_v1"] == "2026-10-18"


def test_failure_in_second_week_keeps_the_first_one_recorded(estado, afd, monkeypatch):
    estado.write_text('{"ultima_semana_v1": "2026-10-04"}', encoding="utf-8")
    enviados = []

    def upload(path, unidade):
        if enviados:
            raise RuntimeError("upload failed")
        enviados.append(path)

    monkeypatch.setattr(main, "enviar_afd_para_servidor", upload)

    resultado = processar("V1", lambda inicio, fim: afd, estado)

    assert resultado.status == "FALHA"
    assert load_state_data(estado)["ultima_semana_v1"] == "2026-10-11"


def test_state_is_not_recorded_when_upload_raises(estado, afd, monkeypatch):
    def failed_upload(path, unidade):
        raise RuntimeError("upload failed")

    monkeypatch.setattr(main, "enviar_afd_para_servidor", failed_upload)

    resultado = processar("V1", lambda inicio, fim: afd, estado)

    assert resultado.status == "FALHA"
    assert load_state_data(estado) == {}


def test_before_next_date_skips_extraction_and_upload(estado, monkeypatch):
    estado.write_text('{"next_audit_at_v1": "2026-11-01T00:05-03:00"}', encoding="utf-8")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("unit work must be skipped while its window is closed")

    monkeypatch.setattr(main, "enviar_afd_para_servidor", fail_if_called)

    assert processar("V1", fail_if_called, estado).status == "FORA_DA_JANELA"


def test_forced_week_is_sent_without_touching_state(estado, afd, monkeypatch):
    original = '{"next_audit_at_v1": "2026-11-01T00:05-03:00"}'
    estado.write_text(original, encoding="utf-8")
    monkeypatch.setattr(main, "enviar_afd_para_servidor", lambda path, unidade: None)
    periodos = []

    def extrator(inicio, fim):
        periodos.append((inicio, fim))
        return afd

    semana = datetime(2026, 10, 11, tzinfo=timezone(timedelta(hours=-3)))
    resultado = processar("V1", extrator, estado, semana_forcada=semana)

    assert resultado.status == "OK"
    assert periodos == [("11/10/2026 00:00", "17/10/2026 23:59")]
    assert estado.read_text(encoding="utf-8") == original


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
    monkeypatch.setattr(main, "executar", lambda semana=None: _fake_execucao("FALHA"))
    monkeypatch.setattr(main, "enviar_alerta", lambda execucao, pdf: None)

    assert main.pipeline_principal() == 1

    [arquivo_json] = tmp_path.glob("*.json")
    assert json.loads(arquivo_json.read_text("utf-8"))["status_geral"] == "FALHA"
    [pdf] = tmp_path.glob("*.pdf")
    assert pdf.read_bytes().startswith(b"%PDF")


def test_closed_window_exits_0_without_report_or_alert(tmp_path, monkeypatch):
    monkeypatch.setattr(relatorio, "RELATORIOS_DIR", tmp_path)
    monkeypatch.setattr(main, "executar", lambda semana=None: _fake_execucao("FORA_DA_JANELA"))
    monkeypatch.setattr(main, "enviar_alerta", lambda execucao, pdf: pytest.fail("no alert"))

    assert main.pipeline_principal() == 0
    assert not list(tmp_path.iterdir())


def test_forced_date_becomes_its_sunday(monkeypatch):
    recebido = []
    monkeypatch.setattr(
        main,
        "executar",
        lambda semana=None: recebido.append(semana) or _fake_execucao("FORA_DA_JANELA"),
    )

    main.pipeline_principal(semana=date(2026, 10, 21))

    assert recebido[0].date() == date(2026, 10, 18)
    assert (recebido[0].hour, recebido[0].minute) == (0, 0)
