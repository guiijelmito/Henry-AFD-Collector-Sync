"""Verifica a janela de execução e a ordem de upload no pipeline."""

from ponto_eletronico import main as cli
from ponto_eletronico import pipeline as main
from ponto_eletronico.extractors.henry_v2 import TailnetConnectionError


def test_cli_defaults_to_devtools_menu(monkeypatch):
    import sys
    import types

    monkeypatch.setitem(
        sys.modules, "ponto_eletronico.devtools", types.SimpleNamespace(main=lambda: 7)
    )
    monkeypatch.setattr(cli, "setup_logging", lambda: None)

    assert cli.cli_main([]) == 7


def test_cli_scheduled_option_uses_weekly_pipeline(monkeypatch):
    monkeypatch.setattr(cli, "pipeline_principal", lambda: {"V1": "OK", "V2": "FORA_DA_JANELA"})
    monkeypatch.setattr(cli, "setup_logging", lambda: None)

    assert cli.cli_main(["--scheduled"]) == 0


def test_cursor_registration_happens_after_upload_returns(tmp_path, monkeypatch):
    afd_path = tmp_path / "sample.afd"
    afd_path.write_text("record", encoding="utf-8")
    events = []

    def upload(path, unidade):
        events.append(("upload", unidade, path))

    monkeypatch.setattr(main, "enviar_afd_para_servidor", upload)

    status = main._processar_unidade(
        "V1",
        "1/1",
        lambda: True,
        lambda: str(afd_path),
        lambda: events.append(("cursor", "V1")),
    )

    assert status == "OK"
    assert events == [("upload", "V1", str(afd_path)), ("cursor", "V1")]


def test_cursor_is_not_registered_when_upload_raises(tmp_path, monkeypatch):
    afd_path = tmp_path / "sample.afd"
    afd_path.write_text("record", encoding="utf-8")
    cursor_updates = []

    def failed_upload(path, unidade):
        raise RuntimeError("upload failed")

    monkeypatch.setattr(main, "enviar_afd_para_servidor", failed_upload)

    status = main._processar_unidade(
        "V1",
        "1/1",
        lambda: True,
        lambda: str(afd_path),
        lambda: cursor_updates.append("updated"),
    )

    assert status == "FALHA"
    assert cursor_updates == []


def test_closed_window_skips_extraction_upload_and_cursor_registration(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("unit work must be skipped while its window is closed")

    monkeypatch.setattr(main, "enviar_afd_para_servidor", fail_if_called)

    status = main._processar_unidade(
        "V1",
        "1/1",
        lambda: False,
        lambda: fail_if_called(),
        lambda: fail_if_called(),
    )

    assert status == "FORA_DA_JANELA"


def test_tailnet_connection_failure_has_specific_status_and_message(caplog):
    def connection_failure():
        raise TailnetConnectionError("Não foi possível alcançar o painel V2")

    status = main._processar_unidade("V2", "2/2", lambda: True, connection_failure, lambda: None)

    assert status == "FALHA_TAILSCALE"
    assert "Falha de conexão Tailscale" in caplog.text
