from decimal import Decimal

from emporio.guardrails import amounts_in, unsupported_amounts


def test_reads_the_ways_prices_are_written():
    text = "De R$ 2.199,00 por R$2199, ou R$ 1.000. Parcelas de 183,25 e R$\n50,00."
    assert amounts_in(text) == {Decimal("2199"), Decimal("1000"), Decimal("183.25"), Decimal("50")}


def test_ignores_things_that_are_not_money():
    assert amounts_in("CNPJ 12.345.678/0001-90, pedido 15, 12x, (67) 3341-4444, 7 dias") == set()


def test_amount_from_a_tool_or_the_customer_is_supported():
    reply = "Até R$ 1.000 tem esse: R$ 599,90."
    assert unsupported_amounts(reply, ["violão até R$1000", '{"preco": "R$ 599,90"}']) == set()


def test_invented_amount_is_caught():
    assert unsupported_amounts("Fica R$ 499,90.", ['{"preco": "R$ 599,90"}']) == {Decimal("499.90")}
