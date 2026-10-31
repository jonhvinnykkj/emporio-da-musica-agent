from datetime import date, datetime

import pytest

from emporio.hours import describe, easter, is_holiday


@pytest.mark.parametrize(
    "now, expected",
    [
        (datetime(2026, 10, 28, 14, 0), "aberta até 18:00"),  # Wednesday
        (datetime(2026, 10, 31, 12, 59), "aberta até 13:00"),  # Saturday
        (datetime(2026, 10, 28, 8, 30), "quarta-feira, 28/10 às 09:00"),  # before opening
        (datetime(2026, 10, 28, 18, 0), "quinta-feira, 29/10 às 09:00"),  # closing time
        (datetime(2026, 10, 31, 13, 0), "terça-feira, 03/11 às 09:00"),  # Sunday, then Finados
        (datetime(2026, 11, 2, 10, 0), "terça-feira, 03/11 às 09:00"),  # holiday
    ],
)
def test_describe(now, expected):
    assert expected in describe(now)


@pytest.mark.parametrize(
    "now, expected",
    [
        (datetime(2026, 10, 31, 14, 0), "segunda-feira, 02/11 é feriado, a loja não abre."),
        (datetime(2026, 11, 2, 10, 0), "segunda-feira, 02/11 é feriado, a loja não abre."),
        (datetime(2026, 12, 24, 19, 0), "sexta-feira, 25/12 é feriado, a loja não abre."),
    ],
)
def test_describe_names_the_holiday_the_store_skips(now, expected):
    assert expected in describe(now)


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 10, 24, 14, 0),  # plain weekend
        datetime(2026, 10, 28, 19, 0),  # plain weeknight
        datetime(2026, 10, 28, 14, 0),  # open
        datetime(2026, 11, 14, 14, 0),  # 15/11 is a Sunday: closed anyway, nothing to warn
    ],
)
def test_describe_only_mentions_a_holiday_that_changes_the_answer(now):
    assert "feriado" not in describe(now)


@pytest.mark.parametrize("day", [date(2026, 11, 2), date(2026, 11, 20), date(2026, 4, 3), date(2027, 3, 26)])
def test_national_holidays_include_finados_and_good_friday(day):
    assert is_holiday(day)


@pytest.mark.parametrize("day", [date(2026, 11, 3), date(2026, 4, 4), date(2026, 10, 28)])
def test_ordinary_days_are_not_holidays(day):
    assert not is_holiday(day)


@pytest.mark.parametrize("year, expected", [(2026, date(2026, 4, 5)), (2027, date(2027, 3, 28))])
def test_easter(year, expected):
    assert easter(year) == expected


def test_saturday_afternoon_before_finados():
    assert "terça-feira, 03/11 às 09:00" in describe(datetime(2026, 10, 31, 14, 0))
