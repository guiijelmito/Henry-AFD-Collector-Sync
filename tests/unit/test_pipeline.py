"""Verifica a janela de execução e a ordem de upload no pipeline."""

import json
from datetime import datetime

import pytest

from ponto_eletronico import config, relatorio
from ponto_eletronico import pipeline as main
from ponto_eletronico.extractors.henry_v2 import TailnetConnectionError


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(config, "TENTATIVAS", 3)
    monkeypatch.setattr(main, "_dormir", lambda segundos: None)


def test_cursor_registration_happens_after_upload_returns(tmp_path, monkeypatch):
    afd_path = tmp_path / "sample.afd"
    afd_path.write_text("record", encoding="utf-8")
    events = []

    def upload(path, unidade):
        events.append(("upload", unidade, path))

    monkeypatch.setattr(main, "enviar_afd_para_servidor", upload)

    resultado = main._processar_unidade(
        "V1",
        "1/1",
        lambda: True,
        lambda: str(afd_path),
        lambda: events.append(("cursor", "V1")),
    )

    assert resultado.status == "OK"
    assert events == [("upload", "V1", str(afd_path)), ("cursor", "V1")]


def test_cursor_is_not_registered_when_upload_raises(tmp_path, monkeypatch):
    afd_path = tmp_path / "sample.afd"
    afd_path.write_text("record", encoding="utf-8")
    cursor_updates = []

    def failed_upload(path, unidade):
        raise RuntimeError("upload failed")

    monkeypatch.setattr(main, "enviar_afd_para_servidor", failed_upload)

    resultado = main._processar_unidade(
        "V1",
        "1/1",
        lambda: True,
        lambda: str(afd_path),
        lambda: cursor_updates.append("updated"),
    )

    assert resultado.status == "FALHA"
    assert cursor_updates == []


def test_closed_window_skips_extraction_upload_and_cursor_registration(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("unit work must be skipped while its window is closed")

    monkeypatch.setattr(main, "enviar_afd_para_servidor", fail_if_called)

    resultado = main._processar_unidade(
        "V1",
        "1/1",
        lambda: False,
        lambda: fail_if_called(),
        lambda: fail_if_called(),
    )

    assert resultado.status == "FORA_DA_JANELA"


def test_tailnet_connection_failure_has_specific_status_and_message(caplog):
    def connection_failure():
        raise TailnetConnectionError("Não foi possível alcançar o painel V2")

    resultado = main._processar_unidade("V2", "2/2", lambda: True, connection_failure, lambda: None)

    assert resultado.status == "FALHA_TAILSCALE"
    assert "Tailscale" in resultado.o_que_fazer
    assert "Falha de conexão Tailscale" in caplog.text


def test_temporary_download_failure_is_retried(tmp_path, monkeypatch):
    afd_path = tmp_path / "sample.afd"
    afd_path.write_text("record", encoding="utf-8")
    monkeypatch.setattr(main, "enviar_afd_para_servidor", lambda path, unidade: None)
    attempts = []

    def unstable_download():
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("net::ERR_CONNECTION_TIMED_OUT")
        return str(afd_path)

    resultado = main._processar_unidade("V1", "1/1", lambda: True, unstable_download, lambda: None)

    assert resultado.status == "OK"
    assert len(attempts) == 3


def test_upload_failure_after_all_attempts_explains_what_to_do(tmp_path, monkeypatch):
    afd_path = tmp_path / "sample.afd"
    afd_path.write_text("record", encoding="utf-8")
    attempts = []

    def failed_upload(path, unidade):
        attempts.append(1)
        raise RuntimeError("Timeout 15000ms exceeded")

    monkeypatch.setattr(main, "enviar_afd_para_servidor", failed_upload)

    resultado = main._processar_unidade(
        "V1", "1/1", lambda: True, lambda: str(afd_path), lambda: None
    )

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
    monkeypatch.setattr(main, "executar", lambda: _fake_execucao("FALHA"))
    monkeypatch.setattr(main, "enviar_alerta", lambda execucao, pdf: None)

    assert main.pipeline_principal() == 1

    [arquivo_json] = tmp_path.glob("*.json")
    assert json.loads(arquivo_json.read_text("utf-8"))["status_geral"] == "FALHA"
    [pdf] = tmp_path.glob("*.pdf")
    assert pdf.read_bytes().startswith(b"%PDF")


def test_closed_window_exits_0_without_report_or_alert(tmp_path, monkeypatch):
    monkeypatch.setattr(relatorio, "RELATORIOS_DIR", tmp_path)
    monkeypatch.setattr(main, "executar", lambda: _fake_execucao("FORA_DA_JANELA"))
    monkeypatch.setattr(main, "enviar_alerta", lambda execucao, pdf: pytest.fail("no alert"))

    assert main.pipeline_principal() == 0
    assert not list(tmp_path.iterdir())
