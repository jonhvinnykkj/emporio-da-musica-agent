import json
from datetime import date

import pytest

from emporio.store import Store
from emporio.tools import MAX_FAILED_CHECKS, StoreData, Toolbox, tool_definitions

ANA_PHONE = "(67) 99654-7821"


@pytest.fixture(scope="module")
def data(data_dir):
    return StoreData.load(data_dir)


@pytest.fixture
def box(data):
    return Toolbox(data, Store(), "s1", date(2026, 10, 28))


def call(box, name, **arguments):
    output, is_error = box.run(name, arguments)
    return json.loads(output), is_error


def test_every_tool_has_a_handler(box, data):
    assert {tool["name"] for tool in tool_definitions(list(data.catalog.categories.values()))} == set(
        box.handlers
    )


def test_order_needs_the_right_contact(box):
    assert call(box, "get_order", order_id=8, contact=ANA_PHONE)[0]["status"] == "Enviado"
    wrong, _ = call(box, "get_order", order_id=8, contact="(67) 90000-0000")
    assert wrong["verificado"] is False and "status" not in wrong


def test_missing_order_and_wrong_contact_get_the_same_answer(box):
    assert (
        call(box, "get_order", order_id=999, contact=ANA_PHONE)[0]
        == call(box, "get_order", order_id=8, contact="(67) 90000-0000")[0]
    )


def test_session_locks_after_repeated_failures(box):
    for _ in range(MAX_FAILED_CHECKS):
        call(box, "get_order", order_id=8, contact="(67) 90000-0000")
    locked, _ = call(box, "get_order", order_id=8, contact=ANA_PHONE)
    assert "open_ticket" in locked["mensagem"] and "status" not in locked


def test_quote_mixes_promotional_and_regular_items(box):
    result, _ = call(
        box,
        "quote_order",
        items=[{"product_id": 81, "quantity": 2}, {"product_id": 121, "quantity": 1}],
        city="Campo Grande",
    )
    assert result["subtotal"] == "R$ 1.639,00"  # 599.90 x 2 + 439.20
    assert result["total_no_pix"] == "R$ 1.579,01"  # PIX only on the two regular items
    assert result["frete"] == "Grátis"


def test_quote_charges_metro_shipping_under_500(box):
    result, _ = call(box, "quote_order", items=[{"product_id": 116, "quantity": 1}], city="campo grande")
    assert result["frete"] == "R$ 35,00"
    assert result["total_com_frete"] == "R$ 234,90"


def test_quote_does_not_invent_shipping_for_other_cities(box):
    result, _ = call(box, "quote_order", items=[{"product_id": 81, "quantity": 1}], city="Dourados")
    assert "CEP" in result["frete"] and "total_com_frete" not in result


def test_quote_rejects_quantity_above_stock_and_items_not_for_sale(box):
    result, _ = call(
        box, "quote_order", items=[{"product_id": 93, "quantity": 3}, {"product_id": 130, "quantity": 1}]
    )
    assert len(result["problemas"]) == 2 and result["itens"] == []


def test_ticket_returns_a_protocol(box):
    result, _ = call(box, "open_ticket", kind="reclamacao", summary="Atraso na entrega", order_id=8)
    assert result["protocolo"] == "EM-00001"
    assert result["prazo_de_retorno"] == "24 horas úteis"


def test_only_complaints_promise_a_return_time(box):
    assert "prazo_de_retorno" not in call(box, "open_ticket", kind="duvida", summary="Sem regra")[0]


def test_bad_arguments_come_back_as_an_error(box):
    assert call(box, "get_order", order_id=8)[1] is True
    assert call(box, "no_such_tool")[1] is True


def test_no_tool_exposes_customer_contact_data(box, data):
    output = json.dumps(
        [
            call(box, "get_order", order_id=8, contact=ANA_PHONE)[0],
            call(box, "check_return", order_id=8, contact=ANA_PHONE, reason="defeito")[0],
        ],
        ensure_ascii=False,
    )
    for customer in data.orders.customers.values():
        assert customer["email"] not in output and customer["phone"] not in output
