"""Confirmação do upload pelo painel e comandos de linha de comando."""

import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

from ponto_eletronico import config
from ponto_eletronico.cloud import UploadRecusado, UploadSemConfirmacao, _conferir_resposta

RAIZ = Path(__file__).resolve().parents[2]


def test_http_200_confirms_the_upload():
    _conferir_resposta(200, "V1")


@pytest.mark.parametrize("status", [400, 401, 403])
def test_4xx_means_refused_and_nothing_saved(status):
    with pytest.raises(UploadRecusado):
        _conferir_resposta(status, "V1")


@pytest.mark.parametrize("status", [500, 502, 504, 302])
def test_other_status_means_unknown_result(status):
    with pytest.raises(UploadSemConfirmacao):
        _conferir_resposta(status, "V2")


@pytest.fixture
def cli(tmp_path, monkeypatch):
    estado = tmp_path / "estado_ponto.json"
    monkeypatch.setattr(config, "ARQUIVO_ESTADO", estado)
    spec = importlib.util.spec_from_file_location("main_cli", RAIZ / "main.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.main, estado


def test_resolve_doubtful_day_as_present_in_panel(cli):
    main, estado = cli
    estado.write_text('{"dias_duvidosos_v1": ["2026-11-13"]}', encoding="utf-8")

    codigo = main(
        ["--resolver-duvidoso", "2026-11-13", "--unidade", "V1", "--esta-no-painel", "sim"]
    )

    assert codigo == 0
    assert json.loads(estado.read_text("utf-8")) == {"dias_avulsos_v1": ["2026-11-13"]}


def test_resolve_unknown_doubtful_day_fails(cli):
    main, _ = cli
    codigo = main(
        ["--resolver-duvidoso", "2026-11-13", "--unidade", "V2", "--esta-no-painel", "nao"]
    )
    assert codigo == 2


def test_resolve_requires_unit_and_answer(cli):
    main, _ = cli
    with pytest.raises(SystemExit):
        main(["--resolver-duvidoso", "2026-11-13"])


def test_day_and_week_cannot_be_combined(cli):
    main, _ = cli
    with pytest.raises(SystemExit):
        main(["--dia", "2026-11-13", "--semana", "2026-11-08"])


def test_day_option_is_passed_to_the_pipeline(cli, monkeypatch):
    main, _ = cli
    from ponto_eletronico import pipeline

    recebido = []
    monkeypatch.setattr(
        pipeline, "pipeline_principal", lambda dias=None: recebido.append(dias) or 0
    )

    assert main(["--dia", "2026-11-12", "--dia", "2026-11-13"]) == 0
    assert recebido == [[date(2026, 11, 12), date(2026, 11, 13)]]


def test_mark_manual_uploads_for_both_units(cli):
    main, estado = cli
    estado.write_text('{"dias_duvidosos_v2": ["2026-11-09"]}', encoding="utf-8")

    codigo = main(
        ["--marcar-enviado", "2026-11-09", "--marcar-enviado", "2026-11-08", "--unidade", "todas"]
    )

    assert codigo == 0
    assert json.loads(estado.read_text("utf-8")) == {
        "dias_duvidosos_v2": ["2026-11-09"],  # duvidoso continua pedindo conferência
        "dias_avulsos_v1": ["2026-11-08", "2026-11-09"],
        "dias_avulsos_v2": ["2026-11-08"],
    }


def test_mark_manual_upload_requires_unit(cli):
    main, _ = cli
    with pytest.raises(SystemExit):
        main(["--marcar-enviado", "2026-11-08"])


def test_resolve_doubtful_does_not_accept_all_units(cli):
    main, _ = cli
    with pytest.raises(SystemExit):
        main(["--resolver-duvidoso", "2026-11-08", "--unidade", "todas", "--esta-no-painel", "sim"])


def test_queue_start_for_one_unit(cli):
    main, estado = cli
    assert main(["--inicio-fila", "2026-11-08", "--unidade", "V1"]) == 0
    assert json.loads(estado.read_text("utf-8")) == {"ultimo_dia_v1": "2026-11-07"}


def test_queue_start_refuses_to_move_back(cli):
    main, estado = cli
    estado.write_text('{"ultimo_dia_v1": "2026-11-17"}', encoding="utf-8")
    assert main(["--inicio-fila", "2026-11-08", "--unidade", "V1"]) == 2
    assert json.loads(estado.read_text("utf-8")) == {"ultimo_dia_v1": "2026-11-17"}
