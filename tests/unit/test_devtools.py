from datetime import datetime, timedelta, timezone

from ponto_eletronico import devtools
from ponto_eletronico.devtools import (
    confirmar_upload,
    criar_downloaders,
    processar_unidades,
    resumir_arquivo,
    selecionar_unidades,
    solicitar_intervalo_manual,
)


def test_manual_interval_prompts_for_both_dates_and_retries_invalid_ranges():
    now = datetime(2026, 10, 20, 15, tzinfo=timezone(timedelta(hours=-3)))
    answers = iter(
        [
            "bad",  # início inválido
            "22/10/2026",
            "bad",  # fim inválido
            "22/10/2026",
            "19/10/2026",  # fim anterior ao início
            "10/10/2026",
            "12/10/2026",  # intervalo válido
        ]
    )
    messages = []

    interval = solicitar_intervalo_manual(lambda _: next(answers), messages.append, now)

    assert interval == ("10/10/2026 00:00", "12/10/2026 23:59")
    assert any("Data inicial inválida" in message for message in messages)
    assert any("Data final inválida" in message for message in messages)
    assert any("não pode ser anterior" in message for message in messages)


def test_manual_interval_same_day_covers_the_entire_day():
    now = datetime(2026, 10, 20, 15, 30, tzinfo=timezone(timedelta(hours=-3)))
    answers = iter(["20/10/2026", "20/10/2026"])

    assert solicitar_intervalo_manual(lambda _: next(answers), lambda _: None, now) == (
        "20/10/2026 00:00",
        "20/10/2026 23:59",
    )


def test_devtools_downloaders_use_manual_interval_without_browser_delays(monkeypatch):
    calls = []

    monkeypatch.setattr(
        devtools,
        "automatizar_download_afd_v1",
        lambda **kwargs: calls.append(("V1", kwargs)),
    )
    monkeypatch.setattr(
        devtools,
        "automatizar_download_afd_v2",
        lambda **kwargs: calls.append(("V2", kwargs)),
    )

    interval = ("20/10/2026 00:00", "22/10/2026 23:59")
    downloaders = criar_downloaders(interval)
    downloaders["V1"]()
    downloaders["V2"]()

    assert calls == [
        (
            "V1",
            {
                "intervalo_manual": interval,
                "headless": False,
                "slow_mo_ms": 0,
            },
        ),
        (
            "V2",
            {
                "intervalo_manual": interval,
                "headless": False,
                "slow_mo_ms": 0,
            },
        ),
    ]


def test_default_devtools_upload_is_visible_and_slow(tmp_path, monkeypatch):
    path = tmp_path / "v1.txt"
    path.write_text("000000010record-a\n", encoding="utf-8")
    upload_calls = []

    def upload(file_path, *, unidade, headless, slow_mo_ms):
        upload_calls.append((file_path, unidade, headless, slow_mo_ms))

    monkeypatch.setattr(devtools, "enviar_afd_para_servidor", upload)

    result = processar_unidades(
        ("V1",),
        enviar=True,
        downloaders={"V1": lambda: path},
        output_fn=lambda _: None,
    )

    assert result == {"V1": "ENVIADO"}
    assert upload_calls == [(str(path), "V1", False, 0)]


def test_selecionar_unidades_retries_invalid_choice_and_supports_both():
    answers = iter(["x", "3"])
    messages = []

    selected = selecionar_unidades(lambda _: next(answers), messages.append)

    assert selected == ("V1", "V2")
    assert any("Opção inválida" in message for message in messages)


def test_selecionar_unidades_can_cancel():
    assert selecionar_unidades(lambda _: "0", lambda _: None) == ()


def test_confirmar_upload_defaults_to_no_and_accepts_yes():
    assert not confirmar_upload(lambda _: "", lambda _: None)
    assert confirmar_upload(lambda _: "sim", lambda _: None)


def test_resumir_arquivo_reports_size_and_nsr_range_without_record_contents(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text(
        "000000010record-a\n000000012record-b\nheader\n",
        encoding="utf-8",
    )

    summary = resumir_arquivo(path)

    assert f"{path.stat().st_size} bytes" in summary
    assert "2 registros" in summary
    assert "NSR 000000010-000000012" in summary
    assert "record-a" not in summary


def test_processar_unidades_isolates_download_failures_and_skips_upload(tmp_path):
    path = tmp_path / "v1.txt"
    path.write_text("000000010record-a\n", encoding="utf-8")
    uploads = []
    messages = []

    def failed_download():
        raise RuntimeError("clock unavailable")

    result = processar_unidades(
        ("V1", "V2"),
        enviar=False,
        downloaders={"V1": lambda: path, "V2": failed_download},
        uploader=lambda file_path, unit: uploads.append((file_path, unit)),
        output_fn=messages.append,
    )

    assert result == {"V1": "BAIXADO", "V2": "FALHA_DOWNLOAD"}
    assert uploads == []
    assert any("clock unavailable" in message for message in messages)


def test_processar_unidades_asks_before_upload_and_only_uploads_downloaded_files(tmp_path):
    path = tmp_path / "v2.txt"
    path.write_text("000000020record-b\n", encoding="utf-8")
    uploads = []

    result = processar_unidades(
        ("V2",),
        enviar=None,
        downloaders={"V2": lambda: path},
        uploader=lambda file_path, unit: uploads.append((file_path, unit)),
        output_fn=lambda _: None,
        input_fn=lambda _: "s",
    )

    assert result == {"V2": "ENVIADO"}
    assert uploads == [(str(path), "V2")]


def test_processar_unidades_can_keep_file_local(tmp_path):
    path = tmp_path / "v1.txt"
    path.write_text("000000010record-a\n", encoding="utf-8")
    uploads = []

    result = processar_unidades(
        ("V1",),
        enviar=None,
        downloaders={"V1": lambda: path},
        uploader=lambda file_path, unit: uploads.append((file_path, unit)),
        output_fn=lambda _: None,
        input_fn=lambda _: "n",
    )

    assert result == {"V1": "BAIXADO"}
    assert uploads == []
