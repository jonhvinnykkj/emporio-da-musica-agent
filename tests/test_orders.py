from datetime import date

import pytest

from emporio.catalog import Catalog
from emporio.orders import OrderBook


@pytest.fixture(scope="module")
def book(data_dir):
    return OrderBook(data_dir, Catalog(data_dir))


@pytest.mark.parametrize(
    "phone",
    [
        "(67) 99654-7821",
        "67996547821",
        "996547821",
        "+55 67 99654-7821",
        "5567996547821",
        "067 99654 7821",
    ],
)
def test_phone_formats_are_accepted(book, phone):
    assert book.verified_order(8, phone).id == 8


@pytest.mark.parametrize(
    "phone", ["96547821", "7821", "", "anacarol.ferreira@coldmail.com", "(67) 99812-3456"]
)
def test_partial_or_wrong_contact_is_refused(book, phone):
    assert book.verified_order(8, phone) is None


def test_missing_order_looks_the_same_as_wrong_contact(book):
    assert book.verified_order(999, "(67) 99654-7821") is None


def test_view_has_first_name_and_no_contact_data(book):
    view = book.view(book.orders[8], date(2026, 10, 31))
    assert view["cliente_primeiro_nome"] == "Ana"
    text = str(view)
    assert "coldmail" not in text and "99654" not in text and "Ferreira" not in text


def test_order_8_is_245_days_past_its_estimate(book):
    view = book.view(book.orders[8], date(2026, 10, 31))
    assert view["dias_desde_a_previsao"] == 245 and view["requer_atencao"] is True


@pytest.mark.parametrize("days_old, expected", [(15, False), (16, True)])
def test_stalled_order_boundary(book, days_old, expected):
    order = book.orders[13]
    today = date.fromordinal(order.date.toordinal() + days_old)
    assert book.view(order, today)["requer_atencao"] is expected


def test_shipped_order_is_fine_on_the_estimated_day(book):
    order = book.orders[8]
    assert book.view(order, order.estimated_delivery)["requer_atencao"] is False


def test_view_uses_recorded_value_and_plain_status(book):
    view = book.view(book.orders[13], date(2026, 3, 13))
    assert view["valor_registrado"] == "R$ 1.899,00" and view["status"] == "Pendente"


def test_delivered_order_never_needs_attention(book):
    assert book.view(book.orders[1], date(2026, 10, 31))["requer_atencao"] is False


def test_view_shows_cancellation_reason_only_when_cancelled(book):
    today = date(2026, 10, 31)
    cancelled = book.view(book.orders[18], today)
    assert cancelled["status"] == "Cancelado"
    assert "fora de estoque" in cancelled["motivo_cancelamento"]
    assert "motivo_cancelamento" not in book.view(book.orders[8], today)
