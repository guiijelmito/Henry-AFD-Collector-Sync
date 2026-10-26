import json
from datetime import datetime, timedelta, timezone

import pytest

from ponto_eletronico.state_store import (
    StateIntegrityError,
    is_audit_due,
    load_state_data,
    pending_weeks,
    record_week_sent,
    week_range,
    week_start,
)

TZ = timezone(timedelta(hours=-3))
FRIDAY = datetime(2026, 10, 23, 23, 59, tzinfo=TZ)
SUNDAY_18 = datetime(2026, 10, 18, tzinfo=TZ)
SUNDAY_25 = datetime(2026, 10, 25, tzinfo=TZ)


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize(
    "moment",
    [
        SUNDAY_18,
        datetime(2026, 10, 20, 15, 30, tzinfo=TZ),
        datetime(2026, 10, 24, 23, 59, tzinfo=TZ),
    ],
)
def test_week_starts_on_sunday_midnight(moment):
    assert week_start(moment) == SUNDAY_18


def test_week_range_goes_from_sunday_to_saturday_23_59():
    assert week_range(SUNDAY_18) == ("18/10/2026 00:00", "24/10/2026 23:59")


def test_without_state_collects_the_last_closed_week(tmp_path):
    monday = datetime(2026, 10, 26, 0, 5, tzinfo=TZ)

    assert pending_weeks(tmp_path / "missing.json", "v1", monday) == [SUNDAY_18]


def test_week_is_pending_only_after_saturday_23_59(tmp_path):
    state_path = tmp_path / "state.json"
    write(state_path, {"ultima_semana_v1": "2026-10-11"})
    saturday_late = datetime(2026, 10, 24, 23, 59, tzinfo=TZ)

    assert pending_weeks(state_path, "v1", saturday_late) == []
    assert pending_weeks(state_path, "v1", SUNDAY_25) == [SUNDAY_18]


def test_late_run_recovers_missed_weeks_in_order_up_to_the_limit(tmp_path):
    state_path = tmp_path / "state.json"
    write(state_path, {"ultima_semana_v2": "2026-09-06"})
    sunday_nov_1 = datetime(2026, 11, 1, 0, 5, tzinfo=TZ)

    weeks = pending_weeks(state_path, "v2", sunday_nov_1, limit=4)

    assert [w.date().isoformat() for w in weeks] == [
        "2026-09-13",
        "2026-09-20",
        "2026-09-27",
        "2026-10-04",
    ]


def test_record_week_sent_schedules_sunday_00_05_after_next_week(tmp_path):
    state_path = tmp_path / "state.json"

    record_week_sent(state_path, "v1", SUNDAY_18)

    assert load_state_data(state_path) == {
        "ultima_semana_v1": "2026-10-18",
        "next_audit_at_v1": "2026-11-01T00:05-03:00",
    }
    assert not list(tmp_path.glob("*.tmp"))


def test_next_date_is_the_same_whatever_day_the_week_was_sent(tmp_path):
    state_path = tmp_path / "state.json"
    write(state_path, {"ultima_semana_v1": "2026-10-11"})

    [week] = pending_weeks(state_path, "v1", datetime(2026, 10, 29, 10, 0, tzinfo=TZ))
    record_week_sent(state_path, "v1", week)

    assert load_state_data(state_path)["next_audit_at_v1"] == "2026-11-01T00:05-03:00"


def test_collection_is_allowed_at_or_after_next_date_on_any_day(tmp_path):
    state_path = tmp_path / "state.json"
    write(state_path, {"next_audit_at_v1": "2026-10-23T23:59:00-03:00"})

    assert not is_audit_due(state_path, "v1", FRIDAY - timedelta(minutes=1))
    assert is_audit_due(state_path, "v1", FRIDAY)
    assert is_audit_due(state_path, "v1", FRIDAY + timedelta(days=1))


def test_first_audit_is_allowed_without_state(tmp_path):
    assert is_audit_due(tmp_path / "missing.json", "v1", FRIDAY)


def test_legacy_keys_are_read_and_then_replaced(tmp_path):
    state_path = tmp_path / "state.json"
    write(
        state_path,
        {
            "next_date": "2026-10-30",
            "next_advance_at_v1": "2026-10-23T09:00:00-03:00",
            "collected_until_v1": "2026-10-23T23:59-03:00",
            "next_advance_at_v2": "2026-10-23T09:00:00-03:00",
        },
    )
    assert not is_audit_due(state_path, "v1", FRIDAY - timedelta(days=1))

    record_week_sent(state_path, "v1", SUNDAY_18)

    assert load_state_data(state_path) == {
        "next_advance_at_v2": "2026-10-23T09:00:00-03:00",
        "ultima_semana_v1": "2026-10-18",
        "next_audit_at_v1": "2026-11-01T00:05-03:00",
    }


def test_v1_legacy_next_date_alone_is_respected(tmp_path):
    state_path = tmp_path / "state.json"
    write(state_path, {"next_date": "2026-10-30"})

    assert not is_audit_due(state_path, "v1", FRIDAY)
    assert is_audit_due(state_path, "v2", FRIDAY)


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
        is_audit_due(state_path, "v1", FRIDAY)
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
        record_week_sent(state_path, "v1", SUNDAY_18)
    assert state_path.read_text(encoding="utf-8") == original


def test_unknown_version_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="desconhecida"):
        is_audit_due(tmp_path / "state.json", "v3", FRIDAY)


def test_invalid_last_week_is_rejected(tmp_path):
    state_path = tmp_path / "state.json"
    write(state_path, {"ultima_semana_v1": "18/10/2026"})

    with pytest.raises(StateIntegrityError, match="inválida"):
        pending_weeks(state_path, "v1", FRIDAY)
