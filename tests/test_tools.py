import json
from datetime import datetime

import pytest

from emporio.journal import Journal
from emporio.tools import MAX_FAILED_CHECKS, StoreData, Toolbox, tool_definitions

ANA_PHONE = "(67) 99654-7821"
WRONG_PHONE = "(67) 90000-0000"


@pytest.fixture(scope="module")
def data(data_dir):
    return StoreData.load(data_dir)


@pytest.fixture
def journal_path(tmp_path):
    return tmp_path / "journal.jsonl"


@pytest.fixture
def box(data, journal_path):
    return Toolbox(data, Journal(journal_path), "s1", lambda: datetime(2026, 10, 28, 14, 0))


def call(box, name, **arguments):
    output, is_error = box.run(name, arguments)
    return json.loads(output), is_error


def test_there_are_exactly_four_strict_tools(data):
    tools = tool_definitions(list(data.catalog.categories.values()))
    assert [tool["name"] for tool in tools] == [
        "buscar_produtos",
        "calcular_compra",
        "consultar_pedido",
        "encaminhar_para_equipe",
    ]
    assert all(tool["strict"] is True for tool in tools)


def test_search_translates_portuguese_arguments(box):
    result, _ = call(
        box, "buscar_produtos", categoria="Violões", cordas="aco", eletrico=True, preco_maximo=3000
    )
    assert result["total_encontrado"] > 0
    assert all(p["categoria"] == "Violões" for p in result["produtos"])


def test_search_on_sale_only_lists_promotions(box):
    result, _ = call(box, "buscar_produtos", somente_promocao=True)
    assert result["produtos"] and all(p["promocao_ativa"] for p in result["produtos"])


def test_search_limits_to_five_and_reports_total(box):
    result, _ = call(box, "buscar_produtos")
    assert result["mostrando"] == len(result["produtos"]) == 5 and result["total_encontrado"] > 5


def test_order_needs_the_right_phone(box):
    assert call(box, "consultar_pedido", numero_pedido=8, telefone=ANA_PHONE)[0]["status"] == "Enviado"
    wrong, _ = call(box, "consultar_pedido", numero_pedido=8, telefone=WRONG_PHONE)
    assert wrong["verificado"] is False and "status" not in wrong


def test_wrong_phone_and_missing_order_get_the_same_answer(box):
    assert (
        call(box, "consultar_pedido", numero_pedido=999, telefone=ANA_PHONE)[0]
        == call(box, "consultar_pedido", numero_pedido=8, telefone=WRONG_PHONE)[0]
    )


def test_lock_applies_to_every_order_in_the_session(box):
    for _ in range(MAX_FAILED_CHECKS):
        call(box, "consultar_pedido", numero_pedido=8, telefone=WRONG_PHONE)
    blocked, _ = call(box, "consultar_pedido", numero_pedido=4, telefone="(67) 99812-3456")
    assert "status" not in blocked and blocked["bloqueado"] is True and blocked["verificado"] is False


def test_lock_blocks_even_the_right_phone(box):
    for _ in range(MAX_FAILED_CHECKS):
        call(box, "consultar_pedido", numero_pedido=8, telefone=WRONG_PHONE)
    assert "status" not in call(box, "consultar_pedido", numero_pedido=8, telefone=ANA_PHONE)[0]


def test_two_failures_do_not_lock(box):
    for _ in range(MAX_FAILED_CHECKS - 1):
        answer, _ = call(box, "consultar_pedido", numero_pedido=8, telefone=WRONG_PHONE)
        assert "bloqueado" not in answer
    assert call(box, "consultar_pedido", numero_pedido=8, telefone=ANA_PHONE)[0]["verificado"] is True


def test_the_failure_that_reaches_the_limit_already_reports_the_lock(box):
    answers = [call(box, "consultar_pedido", numero_pedido=8, telefone=WRONG_PHONE)[0] for _ in range(3)]
    assert MAX_FAILED_CHECKS == 3
    assert all("bloqueado" not in answer for answer in answers[:-1])
    assert answers[-1]["bloqueado"] is True


def test_failures_are_counted_per_toolbox(data, journal_path):
    clock = lambda: datetime(2026, 10, 28, 14, 0)  # noqa: E731
    first, second = (Toolbox(data, Journal(journal_path), name, clock) for name in ("a", "b"))
    for _ in range(MAX_FAILED_CHECKS):
        call(first, "consultar_pedido", numero_pedido=8, telefone=WRONG_PHONE)
    assert call(second, "consultar_pedido", numero_pedido=8, telefone=ANA_PHONE)[0]["verificado"] is True


def test_clock_is_read_on_every_call(data, journal_path):
    moments = iter([datetime(2026, 10, 28, 23, 59), datetime(2026, 10, 29, 0, 1)])
    box = Toolbox(data, Journal(journal_path), "s1", lambda: next(moments))
    first = call(box, "consultar_pedido", numero_pedido=8, telefone=ANA_PHONE)[0]
    second = call(box, "consultar_pedido", numero_pedido=8, telefone=ANA_PHONE)[0]
    assert second["dias_desde_a_compra"] == first["dias_desde_a_compra"] + 1


def test_compra_mixes_promotional_and_regular_items(box):
    result, _ = call(
        box,
        "calcular_compra",
        itens=[{"produto_id": 81, "quantidade": 2}, {"produto_id": 121, "quantidade": 1}],
        cidade="Campo Grande",
    )
    assert result["subtotal"] == "R$ 1.639,00"  # 599.90 x 2 + 439.20
    assert result["total_no_pix"] == "R$ 1.579,01"  # PIX only on the two regular items
    assert result["frete"] == "Grátis"


def test_compra_rounds_pix_on_the_line(box):
    result, _ = call(
        box, "calcular_compra", itens=[{"produto_id": 81, "quantidade": 2}], cidade="Campo Grande"
    )
    assert result["total_no_pix_com_frete"] == "R$ 1.139,81"


def test_compra_charges_metro_shipping_under_500(box):
    result, _ = call(
        box, "calcular_compra", itens=[{"produto_id": 116, "quantidade": 1}], cidade="campo grande"
    )
    assert result["frete"] == "R$ 35,00" and result["total_com_frete"] == "R$ 234,90"


def test_compra_never_prices_shipping_for_other_cities(box):
    result, _ = call(box, "calcular_compra", itens=[{"produto_id": 81, "quantidade": 1}], cidade="Dourados")
    assert "total_com_frete" not in result and "total_no_pix_com_frete" not in result
    assert "R$" not in result["frete"]


def test_compra_without_city_does_not_price_shipping(box):
    result, _ = call(box, "calcular_compra", itens=[{"produto_id": 81, "quantidade": 1}])
    assert "total_com_frete" not in result


def test_compra_rejects_items_above_stock_or_not_for_sale(box):
    result, _ = call(
        box,
        "calcular_compra",
        itens=[{"produto_id": 93, "quantidade": 3}, {"produto_id": 130, "quantidade": 1}],
    )
    assert len(result["problemas"]) == 2 and result["itens"] == []


def test_compra_sums_repeated_products_before_checking_stock(box):
    result, _ = call(
        box,
        "calcular_compra",
        itens=[{"produto_id": 93, "quantidade": 2}, {"produto_id": 93, "quantidade": 2}],
    )
    assert result["itens"] == [] and len(result["problemas"]) == 1


@pytest.mark.parametrize("quantity", [0, -1, 1000])
def test_invalid_quantity_is_reported(box, quantity):
    result, _ = call(box, "calcular_compra", itens=[{"produto_id": 81, "quantidade": quantity}])
    assert result["itens"] == [] and result["problemas"]


def test_unknown_product_is_reported(box):
    result, _ = call(box, "calcular_compra", itens=[{"produto_id": 99999, "quantidade": 1}])
    assert result["itens"] == [] and result["problemas"]


def test_handoff_is_recorded_and_masked(box, journal_path):
    result, _ = call(
        box,
        "encaminhar_para_equipe",
        motivo="atendente",
        resumo="Ligar para ana@coldmail.com",
        telefone=ANA_PHONE,
    )
    assert result["encaminhado"] is True
    event = json.loads(journal_path.read_text(encoding="utf-8").splitlines()[-1])
    assert event["kind"] == "encaminhamento" and event["session_id"] == "s1"
    assert event["payload"]["motivo"] == "atendente"
    raw = json.dumps(event)
    assert "coldmail" not in raw and "99654" not in raw and "7821" in raw


def test_only_complaints_promise_a_return_time(box):
    assert (
        call(box, "encaminhar_para_equipe", motivo="reclamacao", resumo="x")[0]["prazo_de_retorno"]
        == "24 horas úteis"
    )
    assert "prazo_de_retorno" not in call(box, "encaminhar_para_equipe", motivo="sem_resposta", resumo="x")[0]


def test_bad_arguments_come_back_as_an_error(box):
    assert call(box, "consultar_pedido", numero_pedido=8)[1] is True
    assert call(box, "no_such_tool")[1] is True


def test_no_tool_exposes_customer_contact_data(box, data):
    output = json.dumps(
        call(box, "consultar_pedido", numero_pedido=8, telefone=ANA_PHONE)[0], ensure_ascii=False
    )
    for customer in data.orders.customers.values():
        assert customer["email"] not in output and customer["phone"] not in output


@pytest.mark.parametrize("city", ["Campo Grande", "Campo Grande - MS", "Campo Grande/MS", "campo grande ms"])
def test_campo_grande_is_recognised_in_common_spellings(box, city):
    result, _ = call(box, "calcular_compra", itens=[{"produto_id": 116, "quantidade": 1}], cidade=city)
    assert result["frete"] == "R$ 35,00"


def test_a_similar_city_name_is_another_city(box):
    result, _ = call(box, "calcular_compra", itens=[{"produto_id": 116, "quantidade": 1}], cidade="Campo Grandeza")
    assert "total_com_frete" not in result
