import json
from datetime import datetime, timedelta, timezone

import pytest

from ponto_eletronico.state_store import (
    StateIntegrityError,
    audit_date_range,
    is_audit_due,
    load_state_data,
    record_audit_upload,
)

TZ = timezone(timedelta(hours=-3))
FRIDAY = datetime(2026, 10, 23, 23, 59, tzinfo=TZ)


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_first_collection_goes_from_monday_to_now_including_friday(tmp_path):
    assert audit_date_range(tmp_path / "missing.json", "v1", FRIDAY) == (
        "19/10/2026 00:00",
        "23/10/2026 23:59",
    )


def test_next_collection_starts_where_the_last_upload_stopped(tmp_path):
    state_path = tmp_path / "state.json"
    write(state_path, {"collected_until_v2": "2026-10-16T23:59-03:00"})

    assert audit_date_range(state_path, "v2", FRIDAY) == (
        "16/10/2026 23:59",
        "23/10/2026 23:59",
    )


def test_upload_is_allowed_at_or_after_next_audit_on_any_day(tmp_path):
    state_path = tmp_path / "state.json"
    write(state_path, {"next_audit_at_v1": "2026-10-23T23:59:00-03:00"})

    assert not is_audit_due(state_path, "v1", FRIDAY - timedelta(minutes=1))
    assert is_audit_due(state_path, "v1", FRIDAY)
    assert is_audit_due(state_path, "v1", FRIDAY + timedelta(days=1))


def test_first_audit_is_allowed_without_state(tmp_path):
    assert is_audit_due(tmp_path / "missing.json", "v1", FRIDAY)


def test_upload_records_collected_until_and_keeps_weekday_and_time(tmp_path):
    state_path = tmp_path / "state.json"
    write(state_path, {"next_audit_at_v1": "2026-10-23T23:59:00-03:00"})
    late_saturday = FRIDAY + timedelta(days=1, hours=3)

    assert record_audit_upload(state_path, "v1", "24/10/2026 22:59", late_saturday)
    assert load_state_data(state_path) == {
        "collected_until_v1": "2026-10-24T22:59-03:00",
        "next_audit_at_v1": "2026-10-30T23:59-03:00",
    }
    assert not list(tmp_path.glob("*.tmp"))


def test_successful_upload_migrates_legacy_schedule_fields(tmp_path):
    state_path = tmp_path / "state.json"
    write(
        state_path,
        {
            "next_advance_at_v1": "2026-10-23T09:00:00-03:00",
            "next_advance_at_v2": "2026-10-23T09:00:00-03:00",
        },
    )

    assert record_audit_upload(state_path, "v1", "23/10/2026 23:59", FRIDAY)
    assert load_state_data(state_path) == {
        "next_advance_at_v2": "2026-10-23T09:00:00-03:00",
        "collected_until_v1": "2026-10-23T23:59-03:00",
        "next_audit_at_v1": "2026-10-30T09:00-03:00",
    }


def test_upload_does_not_write_before_next_audit(tmp_path):
    state_path = tmp_path / "state.json"
    original = {"next_audit_at_v1": "2026-10-24T00:00:00-03:00"}
    write(state_path, original)

    assert not record_audit_upload(state_path, "v1", "23/10/2026 23:59", FRIDAY)
    assert load_state_data(state_path) == original


def test_legacy_v1_next_date_is_migrated_after_upload(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"next_date": "2026-10-01"}', encoding="utf-8")

    assert record_audit_upload(state_path, "v1", "23/10/2026 23:59", FRIDAY)
    assert load_state_data(state_path) == {
        "collected_until_v1": "2026-10-23T23:59-03:00",
        "next_audit_at_v1": "2026-10-29T00:00-03:00",
    }


def test_malformed_json_is_not_treated_as_empty_state(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(StateIntegrityError, match="inválido"):
        is_audit_due(state_path, "v1", FRIDAY)


def test_invalid_audit_timestamp_is_rejected_without_overwriting_state(tmp_path):
    state_path = tmp_path / "state.json"
    original = '{"next_audit_at_v1": "not-a-date"}'
    state_path.write_text(original, encoding="utf-8")

    with pytest.raises(StateIntegrityError, match="inválida"):
        record_audit_upload(state_path, "v1", "23/10/2026 23:59", FRIDAY)
    assert state_path.read_text(encoding="utf-8") == original


def test_failed_temporary_write_preserves_existing_state(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    original = '{"next_audit_at_v1": "2026-10-23T09:00:00-03:00"}'
    state_path.write_text(original, encoding="utf-8")

    def fail_temporary_file(**kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(
        "ponto_eletronico.state_store.tempfile.NamedTemporaryFile", fail_temporary_file
    )
    with pytest.raises(OSError, match="disk unavailable"):
        record_audit_upload(state_path, "v1", "23/10/2026 23:59", FRIDAY)
    assert state_path.read_text(encoding="utf-8") == original


def test_unknown_version_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="desconhecida"):
        is_audit_due(tmp_path / "state.json", "v3", FRIDAY)
