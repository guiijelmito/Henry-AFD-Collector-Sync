"""Testes de integridade e compatibilidade do estado persistido da coleta.

Os casos usam arquivos temporários para comprovar que entradas inválidas não
alteram o cursor real nem sobrescrevem o JSON existente.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from state_store import (
    StateIntegrityError,
    advance_nsr_after_upload,
    is_nsr_advance_due,
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


def test_save_nsr_without_extra_values(tmp_path):
    state_path = tmp_path / "state.json"
    save_nsr(state_path, "v2", "42")

    assert json.loads(state_path.read_text(encoding="utf-8")) == {"last_nsr_v2": "000000042"}


@pytest.mark.parametrize("version", ["v3", "V1"])
def test_state_helpers_reject_unknown_clock_version(tmp_path, version):
    with pytest.raises(ValueError):
        load_nsr(tmp_path / "state.json", version, "1")
    with pytest.raises(ValueError):
        save_nsr(tmp_path / "state.json", version, "1")
    with pytest.raises(ValueError):
        is_nsr_advance_due(tmp_path / "state.json", version)
    with pytest.raises(ValueError):
        advance_nsr_after_upload(tmp_path / "state.json", version, "1")


def test_nsr_normalization_keeps_values_longer_than_nine_digits():
    assert normalize_nsr("1000000000") == "1000000000"


def test_first_successful_upload_starts_window_without_advancing_cursor(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"last_nsr_v1": "100"}', encoding="utf-8")
    now = datetime(2026, 10, 13, 15, tzinfo=timezone(timedelta(hours=-3)))

    advanced = advance_nsr_after_upload(state_path, "v1", "246", now)

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert not advanced
    assert data["last_nsr_v1"] == "100"
    assert data["next_advance_at_v1"] == "2026-10-20T15:00:00-03:00"


def test_window_is_open_before_deadline_and_stays_open_when_run_is_late(tmp_path):
    state_path = tmp_path / "state.json"
    now = datetime(2026, 10, 13, 15, tzinfo=timezone.utc)
    deadline = now + timedelta(days=7)
    state_path.write_text(
        json.dumps({"last_nsr_v1": "100", "next_advance_at_v1": deadline.isoformat()}),
        encoding="utf-8",
    )

    assert not is_nsr_advance_due(state_path, "v1", deadline - timedelta(seconds=1))
    assert is_nsr_advance_due(state_path, "v1", deadline)
    assert is_nsr_advance_due(state_path, "v1", deadline + timedelta(days=1))


def test_upload_inside_window_keeps_cursor_and_schedule(tmp_path):
    state_path = tmp_path / "state.json"
    now = datetime(2026, 10, 13, 15, tzinfo=timezone.utc)
    deadline = now + timedelta(days=7)
    original = {
        "last_nsr_v1": "100",
        "next_advance_at_v1": deadline.isoformat(),
    }
    state_path.write_text(json.dumps(original), encoding="utf-8")

    advanced = advance_nsr_after_upload(
        state_path, "v1", "000000246", deadline - timedelta(seconds=1)
    )

    assert not advanced
    assert json.loads(state_path.read_text(encoding="utf-8")) == original


def test_late_success_advances_once_and_schedules_from_actual_run_time(tmp_path):
    state_path = tmp_path / "state.json"
    initial_run = datetime(2026, 10, 13, 15, tzinfo=timezone.utc)
    deadline = initial_run + timedelta(days=7)
    late_run = deadline + timedelta(days=1)
    state_path.write_text(
        json.dumps({"last_nsr_v1": "100", "next_advance_at_v1": deadline.isoformat()}),
        encoding="utf-8",
    )

    advanced = advance_nsr_after_upload(state_path, "v1", "246", late_run)

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert advanced
    assert data["last_nsr_v1"] == "000000246"
    assert data["next_advance_at_v1"] == (late_run + timedelta(days=7)).isoformat()


def test_legacy_v1_next_date_is_treated_as_due_date_and_migrated(tmp_path):
    state_path = tmp_path / "state.json"
    now = datetime(2026, 10, 13, 15, tzinfo=timezone.utc)
    state_path.write_text(
        json.dumps({"last_nsr_v1": "100", "next_date": "2026-10-06"}),
        encoding="utf-8",
    )

    assert is_nsr_advance_due(state_path, "v1", now)
    assert advance_nsr_after_upload(state_path, "v1", "246", now)

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert "next_date" not in data
    assert data["next_advance_at_v1"] == (now + timedelta(days=7)).isoformat()


def test_v2_has_an_independent_window(tmp_path):
    state_path = tmp_path / "state.json"
    now = datetime(2026, 10, 13, 15, tzinfo=timezone.utc)
    state_path.write_text(
        json.dumps(
            {
                "last_nsr_v1": "100",
                "next_advance_at_v1": (now + timedelta(days=3)).isoformat(),
                "last_nsr_v2": "200",
            }
        ),
        encoding="utf-8",
    )

    assert not is_nsr_advance_due(state_path, "v1", now)
    assert not is_nsr_advance_due(state_path, "v2", now)
    assert not advance_nsr_after_upload(state_path, "v2", "346", now)

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["last_nsr_v1"] == "100"
    assert data["last_nsr_v2"] == "200"
    assert data["next_advance_at_v2"] == (now + timedelta(days=7)).isoformat()


def test_v2_advances_its_cursor_without_touching_v1_or_legacy_key(tmp_path):
    state_path = tmp_path / "state.json"
    now = datetime(2026, 10, 13, 15, tzinfo=timezone.utc)
    state_path.write_text(
        json.dumps(
            {
                "last_nsr_v1": "100",
                "last_nsr_v2": "200",
                "next_date": "2026-10-01",
                "next_advance_at_v2": (now - timedelta(seconds=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    assert advance_nsr_after_upload(state_path, "v2", "346", now)

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["last_nsr_v1"] == "100"
    assert data["last_nsr_v2"] == "000000346"
    assert data["next_date"] == "2026-10-01"


def test_naive_datetime_schedule_uses_local_timezone(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({"next_advance_at_v1": "2026-10-13T15:00:00"}), encoding="utf-8"
    )
    now = datetime(2026, 10, 13, 15)

    assert is_nsr_advance_due(state_path, "v1", now)


def test_invalid_next_advance_at_does_not_overwrite_state(tmp_path):
    state_path = tmp_path / "state.json"
    original = '{"last_nsr_v1": "100", "next_advance_at_v1": "not-a-date"}'
    state_path.write_text(original, encoding="utf-8")
    now = datetime(2026, 10, 13, 15, tzinfo=timezone.utc)

    with pytest.raises(StateIntegrityError):
        advance_nsr_after_upload(state_path, "v1", "246", now)

    assert state_path.read_text(encoding="utf-8") == original


def test_non_text_next_advance_at_is_rejected(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"next_advance_at_v1": 123}', encoding="utf-8")

    with pytest.raises(StateIntegrityError):
        is_nsr_advance_due(state_path, "v1")


def test_failed_temporary_file_creation_preserves_existing_state(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"last_nsr_v1": "100"}', encoding="utf-8")

    def fail_temporary_file(**kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr("state_store.tempfile.NamedTemporaryFile", fail_temporary_file)
    with pytest.raises(OSError, match="disk unavailable"):
        save_nsr(state_path, "v1", "200")

    assert state_path.read_text(encoding="utf-8") == '{"last_nsr_v1": "100"}'
