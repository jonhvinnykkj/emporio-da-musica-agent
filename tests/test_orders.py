from dataclasses import replace
from datetime import date

import pytest

from emporio.orders import format_date, parse_date, payment_label


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


@pytest.mark.parametrize(
    "method, label",
    [
        ("pix", "PIX"),
        ("boleto", "Boleto"),
        ("debit", "Cartão de débito"),
        ("credit_6x", "Cartão de crédito em 6x"),
        ("voucher", "voucher"),
    ],
)
def test_payment_label(method, label):
    assert payment_label(method) == label


def test_dates_are_written_day_first_and_empty_means_none():
    assert format_date(date(2026, 2, 8)) == "08/02/2026"
    assert parse_date("") is None and parse_date("2026-02-28") == date(2026, 2, 28)


def test_shipped_order_view_is_complete(book):
    view = book.view(book.orders[8], date(2026, 3, 1))
    assert view == {
        "pedido": 8,
        "cliente_primeiro_nome": "Ana",
        "data_do_pedido": "15/02/2026",
        "status": "Enviado",
        "valor_registrado": "R$ 349,90",
        "pagamento": "Cartão de débito",
        "itens": [{"produto": book.catalog.products[book.orders[8].items[0][0]].name, "quantidade": 1}],
        "dias_desde_a_compra": 14,
        "requer_atencao": True,
        "codigo_de_rastreio": "BRJL5544332BR",
        "previsao_de_entrega": "28/02/2026",
        "dias_desde_a_previsao": 1,
    }


def test_order_loaded_with_its_status_dates_and_notes(book):
    order = book.orders[18]
    assert (order.customer_id, order.status, order.estimated_delivery) == (17, "cancelled", None)
    assert "fora de estoque" in order.notes and order.items
    shipped = book.orders[8]
    assert shipped.tracking_code == "BRJL5544332BR" and shipped.estimated_delivery == date(2026, 2, 28)


def test_confirmed_order_stalls_after_fifteen_days(book):
    order = book.orders[9]
    on_day_15 = date.fromordinal(order.date.toordinal() + 15)
    assert book.view(order, on_day_15)["requer_atencao"] is False
    assert book.view(order, date.fromordinal(on_day_15.toordinal() + 1))["requer_atencao"] is True


def test_notes_are_hidden_unless_the_order_is_cancelled(book):
    noted = replace(book.orders[1], notes="obs interna")
    assert "motivo_cancelamento" not in book.view(noted, date(2026, 10, 31))
    silent = replace(book.orders[18], notes="")
    assert "motivo_cancelamento" not in book.view(silent, date(2026, 10, 31))
