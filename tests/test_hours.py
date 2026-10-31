from datetime import datetime

import pytest

from emporio.hours import describe


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
