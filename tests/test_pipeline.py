"""Verifica a janela de execução e a ordem de upload no pipeline."""

import main


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
