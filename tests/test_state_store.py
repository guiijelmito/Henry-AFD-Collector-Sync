"""Testes de integridade e compatibilidade do estado persistido da coleta.

Os casos usam arquivos temporários para comprovar que entradas inválidas não
alteram o cursor real nem sobrescrevem o JSON existente.
"""

import json
from datetime import datetime

import pytest

import extract_afc_v1 as extract_v1
from state_store import (
    StateIntegrityError,
    load_nsr,
    load_state_data,
    normalize_nsr,
    save_nsr,
)


def test_missing_state_uses_unit_default(tmp_path):
    assert load_nsr(tmp_path / "state.json", "v1", "45076") == "000045076"


def test_v1_reads_legacy_cursor(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"ultimo_nsr": "123"}', encoding="utf-8")

    assert load_nsr(state_path, "v1", "45076") == "000000123"


def test_v2_uses_default_when_only_legacy_v1_cursor_exists(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"ultimo_nsr": "123"}', encoding="utf-8")

    assert load_nsr(state_path, "v2", "1153") == "000001153"


@pytest.mark.parametrize("contents", ["{", "[]", '"not an object"'])
def test_invalid_state_fails_closed_without_rewriting_file(tmp_path, contents):
    state_path = tmp_path / "state.json"
    state_path.write_text(contents, encoding="utf-8")

    with pytest.raises(StateIntegrityError):
        load_state_data(state_path)
    with pytest.raises(StateIntegrityError):
        save_nsr(state_path, "v1", "900")

    assert state_path.read_text(encoding="utf-8") == contents


@pytest.mark.parametrize("value", [None, True, -1, "12A", "١٢٣"])
def test_nsr_must_be_non_negative_ascii_digits(value):
    with pytest.raises(StateIntegrityError):
        normalize_nsr(value)


def test_save_preserves_other_unit_and_extra_state(tmp_path):
    state_path = tmp_path / "nested" / "state.json"
    state_path.parent.mkdir()
    state_path.write_text(
        json.dumps({"last_nsr_v2": "000000010", "next_date": "2026-10-01"}),
        encoding="utf-8",
    )

    save_nsr(state_path, "v1", "45123", {"next_date": "2026-10-20"})

    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "last_nsr_v1": "000045123",
        "last_nsr_v2": "000000010",
        "next_date": "2026-10-20",
    }
    assert list(state_path.parent.glob("*.tmp")) == []


def test_nsr_normalization_keeps_values_longer_than_nine_digits():
    assert normalize_nsr("1000000000") == "1000000000"


def test_v1_does_not_advance_without_next_date(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"last_nsr_v1": "100"}', encoding="utf-8")
    monkeypatch.setattr(extract_v1, "ARQUIVO_ESTADO", str(state_path))

    extract_v1.salvar_estado("200")

    assert json.loads(state_path.read_text(encoding="utf-8")) == {"last_nsr_v1": "100"}


@pytest.mark.parametrize(
    ("next_date", "should_advance"),
    [("2026-10-06", False), ("2026-10-05", True)],
)
def test_v1_advances_only_when_next_date_is_more_than_seven_days_old(
    tmp_path, monkeypatch, next_date, should_advance
):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 13)

    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({"last_nsr_v1": "100", "next_date": next_date}), encoding="utf-8"
    )
    monkeypatch.setattr(extract_v1, "ARQUIVO_ESTADO", str(state_path))
    monkeypatch.setattr(extract_v1, "datetime", FrozenDateTime)

    extract_v1.salvar_estado("200")

    data = json.loads(state_path.read_text(encoding="utf-8"))
    if should_advance:
        assert data["last_nsr_v1"] == "000000200"
        assert data["next_date"] == "2026-10-20"
    else:
        assert data["last_nsr_v1"] == "100"
        assert data["next_date"] == next_date


def test_v1_invalid_next_date_does_not_overwrite_state(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    original = '{"last_nsr_v1": "100", "next_date": "not-a-date"}'
    state_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(extract_v1, "ARQUIVO_ESTADO", str(state_path))

    with pytest.raises(StateIntegrityError):
        extract_v1.salvar_estado("200")

    assert state_path.read_text(encoding="utf-8") == original
