from datetime import date

import pytest

from emporio.catalog import Catalog
from emporio.orders import OrderBook

TODAY = date(2026, 10, 28)


@pytest.fixture(scope="module")
def book(data_dir):
    return OrderBook(data_dir, Catalog(data_dir))


def replace(order, **changes):
    return order.__class__(**{**order.__dict__, **changes})


@pytest.mark.parametrize(
    "contact",
    [
        "(67) 99654-7821",
        "67996547821",
        "5567996547821",
        "99654-7821",
        "anacarol.ferreira@coldmail.com",
        " ANACAROL.FERREIRA@coldmail.com ",
    ],
)
def test_contact_on_file_unlocks_the_order(book, contact):
    assert book.verified_order(8, contact).id == 8


@pytest.mark.parametrize(
    "contact", ["(67) 99812-3456", "lucas.mendes@jmail.com", "", "7821", "Ana Carolina Ferreira"]
)
def test_someone_else_or_partial_data_does_not_unlock(book, contact):
    assert book.verified_order(8, contact) is None


def test_missing_order_looks_the_same_as_wrong_contact(book):
    assert book.verified_order(999, "(67) 99654-7821") is None


def test_view_has_first_name_and_no_contact_data(book):
    view = book.view(book.orders[8], TODAY)
    assert view["cliente_primeiro_nome"] == "Ana"
    text = str(view)
    assert "coldmail" not in text and "99654" not in text and "Ferreira" not in text


def test_view_flags_overdue_delivery(book):
    assert book.view(book.orders[8], date(2026, 3, 10))["alerta"] == "Entrega atrasada em 10 dias."


def test_view_flags_stalled_order(book):
    assert "sem movimentação" in book.view(book.orders[13], TODAY)["alerta"]


def test_view_shows_cancellation_reason(book):
    assert "fora de estoque" in book.view(book.orders[18], TODAY)["observacao"]


def test_change_of_mind_after_seven_days_is_refused(book):
    decision = book.return_decision(book.orders[4], "arrependimento", TODAY)
    assert decision["elegivel"] is False
    assert decision["secao_do_manual"] == "4.1"
    assert decision["dias_desde_o_recebimento"] == 310


@pytest.mark.parametrize("days_after, eligible", [(7, True), (8, False)])
def test_change_of_mind_boundary(book, days_after, eligible):
    order = book.orders[4]
    today = date.fromordinal(order.estimated_delivery.toordinal() + days_after)
    assert book.return_decision(order, "arrependimento", today)["elegivel"] is eligible


def test_defect_within_thirty_days_is_exchanged(book):
    order = replace(book.orders[4], date=date(2026, 10, 10), estimated_delivery=date(2026, 10, 20))
    decision = book.return_decision(order, "defeito", TODAY)
    assert decision["elegivel"] is True
    assert decision["secao_do_manual"] == "4.2"


def test_defect_within_legal_warranty_goes_to_the_team(book):
    order = replace(book.orders[4], date=date(2026, 8, 20), estimated_delivery=date(2026, 8, 30))
    decision = book.return_decision(order, "defeito", TODAY)
    assert decision["proximo_passo"] == "encaminhar_equipe"
    assert decision["secao_do_manual"] == "8.1"


def test_defect_after_legal_warranty_offers_manufacturer_route(book):
    decision = book.return_decision(book.orders[4], "defeito", TODAY)
    assert decision["elegivel"] is False
    assert decision["proximo_passo"] == "oferecer_intermediacao"


def test_shipped_order_waits_for_receipt(book):
    assert (
        book.return_decision(book.orders[8], "arrependimento", TODAY)["proximo_passo"]
        == "aguardar_recebimento"
    )


def test_unshipped_order_has_no_manual_rule_so_it_goes_to_the_team(book):
    assert (
        book.return_decision(book.orders[11], "arrependimento", TODAY)["proximo_passo"] == "encaminhar_equipe"
    )
