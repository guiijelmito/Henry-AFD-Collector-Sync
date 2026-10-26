from datetime import datetime
from pathlib import Path

import pytest

from ponto_eletronico.afd_validation import (
    AFDRangeValidationError,
    preencher_filtro_data_hora,
    preencher_intervalo_data_hora,
    validar_afd_v1_no_intervalo,
    validar_afd_v2_no_intervalo,
)


class FakeLocator:
    def __init__(self, events, applied_value=None, short_year=True):
        self.value = ""
        self.applied_value = applied_value
        self.actions = []
        self.events = events
        self.short_year = short_year

    def press(self, key):
        self.actions.append(("press", key))
        if key == "Control+A":
            self.value = ""

    def press_sequentially(self, value, delay):
        self.actions.append(("press_sequentially", value, delay))
        self.events.append(("typed", value))
        if len(value) == 10 and value.isdigit():
            parsed = datetime.strptime(value, "%d%m%y%H%M")
            year_format = "%y" if self.short_year else "%Y"
            self.value = parsed.strftime(f"%d/%m/{year_format} %H:%M")
        else:
            self.value = value

    def input_value(self):
        return self.value if self.applied_value is None else self.applied_value


class FakePage:
    def __init__(self, locator):
        self.events = []
        self.fields = {
            "#lblDataI": locator(self.events),
            "#lblDataF": locator(self.events),
        }

    def locator(self, selector):
        return self.fields[selector]


def _registro_marcacao(nsr: int, data: str, hora: str) -> str:
    return f"{nsr:09d}3{data}{hora}" + ("0" * 30)


def _registro_marcacao_v2(nsr: int, timestamp: str) -> str:
    return f"{nsr:09d}3{timestamp}" + ("0" * 20)


def test_preencher_filtro_confere_valor_real_do_campo():
    page = FakePage(FakeLocator)

    preencher_filtro_data_hora(
        page,
        "#lblDataF",
        "19/10/2026 23:59",
    )

    assert page.fields["#lblDataF"].value == "19/10/26 23:59"
    assert page.fields["#lblDataF"].actions == [
        ("press", "Control+A"),
        ("press_sequentially", "1910262359", 75),
        ("press", "Tab"),
    ]


def test_preencher_filtro_falha_se_painel_truncar_horario():
    page = FakePage(lambda events: FakeLocator(events, applied_value="19/10/2026"))

    with pytest.raises(ValueError, match="formato DD/MM/AA HH:MM"):
        preencher_filtro_data_hora(
            page,
            "#lblDataF",
            "19/10/2026 23:59",
        )


def test_preencher_filtro_exige_ano_de_dois_digitos_no_campo():
    page = FakePage(FakeLocator)

    preencher_filtro_data_hora(page, "#lblDataI", "12/10/2026 00:00")

    assert page.fields["#lblDataI"].value == "12/10/26 00:00"
    assert page.fields["#lblDataI"].actions[1] == (
        "press_sequentially",
        "1210260000",
        75,
    )


def test_preencher_filtro_rejeita_ano_exibido_com_quatro_digitos():
    page = FakePage(lambda events: FakeLocator(events, short_year=False))

    with pytest.raises(ValueError, match="formato DD/MM/AA HH:MM"):
        preencher_filtro_data_hora(page, "#lblDataI", "12/10/2026 00:00")


def test_intervalo_preenche_data_inicial_e_final_sem_pausa():
    page = FakePage(FakeLocator)

    preencher_intervalo_data_hora(
        page,
        "12/10/2026 00:00",
        "19/10/2026 23:59",
    )

    assert page.events == [
        ("typed", "1210260000"),
        ("typed", "1910262359"),
    ]


def test_validar_afd_retorna_faixa_e_contagem_no_intervalo(tmp_path: Path):
    path = tmp_path / "valid.afd"
    path.write_text(
        _registro_marcacao(1, "19102026", "0805")
        + "\n"
        + _registro_marcacao(2, "19102026", "1730"),
        encoding="utf-8",
    )

    assert validar_afd_v1_no_intervalo(
        path,
        ("19/10/2026 00:00", "19/10/2026 23:59"),
    ) == (
        datetime(2026, 10, 19, 8, 5),
        datetime(2026, 10, 19, 17, 30),
        2,
    )


def test_validar_afd_rejeita_registros_fora_do_intervalo(tmp_path: Path):
    path = tmp_path / "out-of-range.afd"
    path.write_text(_registro_marcacao(1, "19102020", "0805"), encoding="utf-8")

    with pytest.raises(AFDRangeValidationError, match="fora do intervalo solicitado"):
        validar_afd_v1_no_intervalo(
            path,
            ("19/10/2026 00:00", "19/10/2026 23:59"),
        )


def test_validar_afd_aceita_semana_sem_marcacoes(tmp_path: Path):
    path = tmp_path / "ferias.afd"
    path.write_text("x" * 100, encoding="utf-8")

    assert validar_afd_v1_no_intervalo(path, ("18/10/2026 00:00", "24/10/2026 23:59")) == (
        datetime(2026, 10, 18, 0, 0),
        datetime(2026, 10, 24, 23, 59),
        0,
    )


def test_validar_afd_v2_usa_timestamp_iso8601_do_layout_v2(tmp_path: Path):
    path = tmp_path / "v2.afd"
    path.write_text(
        _registro_marcacao_v2(1, "2026-10-19T08:05:00")
        + "\n"
        + _registro_marcacao_v2(2, "2026-10-19T17:30:00"),
        encoding="utf-8",
    )

    assert validar_afd_v2_no_intervalo(
        path,
        ("19/10/2026 00:00", "19/10/2026 23:59"),
    ) == (
        datetime(2026, 10, 19, 8, 5),
        datetime(2026, 10, 19, 17, 30),
        2,
    )


def test_validar_afd_v2_rejeita_timestamp_fora_do_intervalo(tmp_path: Path):
    path = tmp_path / "v2-out-of-range.afd"
    path.write_text(
        _registro_marcacao_v2(1, "2020-10-19T08:05:00"),
        encoding="utf-8",
    )

    with pytest.raises(AFDRangeValidationError, match="fora do intervalo solicitado"):
        validar_afd_v2_no_intervalo(
            path,
            ("19/10/2026 00:00", "19/10/2026 23:59"),
        )


def test_validar_afd_v2_aceita_segundos_dentro_do_ultimo_minuto(tmp_path: Path):
    path = tmp_path / "v2-last-minute.afd"
    path.write_text(_registro_marcacao_v2(1, "2026-10-23T23:59:30"), encoding="utf-8")

    _, maior, quantidade = validar_afd_v2_no_intervalo(
        path,
        ("19/10/2026 00:00", "23/10/2026 23:59"),
    )
    assert maior == datetime(2026, 10, 23, 23, 59, 30)
    assert quantidade == 1
