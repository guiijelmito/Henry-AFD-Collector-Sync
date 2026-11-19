import json
from datetime import date, datetime, timedelta, timezone

import pytest

from ponto_eletronico.state_store import (
    DUVIDOSO,
    ENVIADO_AGENDADO,
    ENVIADO_AVULSO,
    ENVIADO_SEMANA_ANTIGA,
    StateIntegrityError,
    day_range,
    doubtful_days,
    load_state_data,
    pending_days,
    record_doubtful_day,
    record_extra_day,
    record_scheduled_day,
    resolve_doubtful_day,
    sent_status,
    set_queue_start,
)

TZ = timezone(timedelta(hours=-3))
# Domingo 15/11/2026 às 00:05: o dia fechado mais recente é sábado 14/11
RUN = datetime(2026, 11, 15, 0, 5, tzinfo=TZ)


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_day_range_goes_from_00_00_to_23_59():
    assert day_range(date(2026, 11, 14)) == ("14/11/2026 00:00", "14/11/2026 23:59")


def test_without_state_only_yesterday_is_pending(tmp_path):
    assert pending_days(tmp_path / "s.json", "v1", RUN) == [date(2026, 11, 14)]


def test_day_is_only_closed_a_few_minutes_after_midnight(tmp_path):
    just_after_midnight = datetime(2026, 11, 15, 0, 1, tzinfo=TZ)
    assert pending_days(tmp_path / "s.json", "v1", just_after_midnight) == [date(2026, 11, 13)]


def test_late_run_recovers_missed_days_in_order_up_to_the_limit(tmp_path):
    state_path = tmp_path / "s.json"
    write(state_path, {"ultimo_dia_v1": "2026-11-09"})

    assert pending_days(state_path, "v1", RUN, limit=3) == [
        date(2026, 11, 10),
        date(2026, 11, 11),
        date(2026, 11, 12),
    ]
    assert pending_days(state_path, "v1", RUN) == [
        date(2026, 11, 10) + timedelta(days=n) for n in range(5)
    ]


def test_up_to_date_unit_has_nothing_pending(tmp_path):
    state_path = tmp_path / "s.json"
    write(state_path, {"ultimo_dia_v1": "2026-11-14"})
    assert pending_days(state_path, "v1", RUN) == []


def test_each_unit_has_its_own_queue(tmp_path):
    state_path = tmp_path / "s.json"
    write(state_path, {"ultimo_dia_v1": "2026-11-14", "ultimo_dia_v2": "2026-11-12"})

    assert pending_days(state_path, "v1", RUN) == []
    assert pending_days(state_path, "v2", RUN) == [date(2026, 11, 13), date(2026, 11, 14)]


def test_old_weekly_state_continues_on_the_sunday_after_the_last_week(tmp_path):
    state_path = tmp_path / "s.json"
    write(state_path, {"ultima_semana_v1": "2026-11-01", "next_audit_at_v1": "x"})

    # Semana de 01/11 a 07/11 já enviada: começa no domingo 08/11
    assert pending_days(state_path, "v1", RUN)[0] == date(2026, 11, 8)
    assert sent_status(state_path, "v1", date(2026, 11, 7)) == ENVIADO_AGENDADO


@pytest.mark.parametrize(
    ("data", "day", "expected"),
    [
        ({"ultimo_dia_v1": "2026-11-12"}, date(2026, 11, 12), ENVIADO_AGENDADO),
        ({"ultimo_dia_v1": "2026-11-12"}, date(2026, 11, 13), None),
        ({"dias_avulsos_v1": ["2026-11-13"]}, date(2026, 11, 13), ENVIADO_AVULSO),
        ({"semanas_avulsas_v1": ["2026-11-08"]}, date(2026, 11, 8), ENVIADO_SEMANA_ANTIGA),
        ({"semanas_avulsas_v1": ["2026-11-08"]}, date(2026, 11, 14), ENVIADO_SEMANA_ANTIGA),
        ({"semanas_avulsas_v1": ["2026-11-08"]}, date(2026, 11, 15), None),
        ({"dias_duvidosos_v1": ["2026-11-13"]}, date(2026, 11, 13), DUVIDOSO),
        ({"ultimo_dia_v2": "2026-11-14"}, date(2026, 11, 13), None),  # outra unidade
    ],
)
def test_sent_status_blocks_every_day_already_sent(tmp_path, data, day, expected):
    state_path = tmp_path / "s.json"
    write(state_path, data)
    assert sent_status(state_path, "v1", day) == expected


def test_recording_keeps_the_other_unit_and_old_keys(tmp_path):
    state_path = tmp_path / "s.json"
    write(state_path, {"ultima_semana_v2": "2026-11-01", "semanas_avulsas_v1": ["2026-11-08"]})

    record_scheduled_day(state_path, "v1", date(2026, 11, 14))
    record_extra_day(state_path, "v1", date(2026, 11, 3))
    record_extra_day(state_path, "v1", date(2026, 11, 2))
    record_extra_day(state_path, "v1", date(2026, 11, 3))

    assert load_state_data(state_path) == {
        "ultima_semana_v2": "2026-11-01",
        "semanas_avulsas_v1": ["2026-11-08"],
        "ultimo_dia_v1": "2026-11-14",
        "dias_avulsos_v1": ["2026-11-02", "2026-11-03"],
    }


def test_doubtful_day_confirmed_in_panel_becomes_sent(tmp_path):
    state_path = tmp_path / "s.json"
    record_doubtful_day(state_path, "v1", date(2026, 11, 13))
    assert doubtful_days(state_path, "v1") == [date(2026, 11, 13)]

    resolve_doubtful_day(state_path, "v1", date(2026, 11, 13), is_in_panel=True)

    assert sent_status(state_path, "v1", date(2026, 11, 13)) == ENVIADO_AVULSO
    assert load_state_data(state_path) == {"dias_avulsos_v1": ["2026-11-13"]}


def test_doubtful_day_missing_from_panel_can_be_sent_again(tmp_path):
    state_path = tmp_path / "s.json"
    record_doubtful_day(state_path, "v2", date(2026, 11, 13))

    resolve_doubtful_day(state_path, "v2", date(2026, 11, 13), is_in_panel=False)

    assert sent_status(state_path, "v2", date(2026, 11, 13)) is None
    assert load_state_data(state_path) == {}


def test_resolving_a_day_that_is_not_doubtful_fails(tmp_path):
    with pytest.raises(ValueError, match="não está duvidoso"):
        resolve_doubtful_day(tmp_path / "s.json", "v1", date(2026, 11, 13), is_in_panel=True)


def test_malformed_json_is_not_treated_as_empty_state(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(StateIntegrityError, match="inválido"):
        pending_days(state_path, "v1", RUN)


def test_invalid_date_is_rejected_without_overwriting_state(tmp_path):
    state_path = tmp_path / "state.json"
    original = '{"ultimo_dia_v1": "14/11/2026"}'
    state_path.write_text(original, encoding="utf-8")

    with pytest.raises(StateIntegrityError, match="inválida"):
        pending_days(state_path, "v1", RUN)
    assert state_path.read_text(encoding="utf-8") == original


def test_list_keys_must_be_lists(tmp_path):
    state_path = tmp_path / "state.json"
    write(state_path, {"dias_avulsos_v1": "2026-11-13"})

    with pytest.raises(StateIntegrityError, match="lista"):
        sent_status(state_path, "v1", date(2026, 11, 13))


def test_failed_temporary_write_preserves_existing_state(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    original = '{"ultimo_dia_v1": "2026-11-10"}'
    state_path.write_text(original, encoding="utf-8")

    def fail_temporary_file(**kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(
        "ponto_eletronico.state_store.tempfile.NamedTemporaryFile", fail_temporary_file
    )
    with pytest.raises(OSError, match="disk unavailable"):
        record_scheduled_day(state_path, "v1", date(2026, 11, 11))
    assert state_path.read_text(encoding="utf-8") == original


def test_unknown_version_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="desconhecida"):
        pending_days(tmp_path / "state.json", "v3", RUN)


def test_queue_start_on_empty_unit_recovers_from_that_day(tmp_path):
    state_path = tmp_path / "s.json"
    write(state_path, {"dias_avulsos_v1": ["2026-11-12", "2026-11-13"]})

    set_queue_start(state_path, "v1", date(2026, 11, 12))

    assert load_state_data(state_path)["ultimo_dia_v1"] == "2026-11-11"
    assert pending_days(state_path, "v1", RUN)[0] == date(2026, 11, 12)
    assert sent_status(state_path, "v1", date(2026, 11, 12)) == ENVIADO_AVULSO


def test_queue_start_never_moves_back(tmp_path):
    state_path = tmp_path / "s.json"
    write(state_path, {"ultima_semana_v2": "2026-11-01"})  # enviado até 07/11

    with pytest.raises(ValueError, match="voltar a fila"):
        set_queue_start(state_path, "v2", date(2026, 11, 5))
    set_queue_start(state_path, "v2", date(2026, 11, 8))
    assert load_state_data(state_path)["ultimo_dia_v2"] == "2026-11-07"
