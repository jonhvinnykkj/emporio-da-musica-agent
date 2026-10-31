from decimal import Decimal

from emporio.guardrails import amounts_in, unsupported_amounts


def test_reads_the_ways_prices_are_written():
    text = "De R$ 2.199,00 por R$2199, ou R$ 1.000. Parcelas de R$ 183,25 e R$\n50,00."
    assert amounts_in(text) == {Decimal("2199"), Decimal("1000"), Decimal("183.25"), Decimal("50")}


def test_reads_dot_as_decimal_only_with_two_final_digits():
    assert amounts_in("R$ 1199.80 ou R$ 1.199 ou R$ 1.199,80") == {Decimal("1199.80"), Decimal("1199")}


def test_only_prefixed_values_count():
    assert amounts_in("12x de 183,25 e 7 dias") == set()


def test_ignores_things_that_are_not_money():
    assert amounts_in("CNPJ 12.345.678/0001-90, pedido 15, 12x, (67) 3341-4444, 7 dias") == set()


def test_amount_from_a_tool_or_the_customer_is_supported():
    reply = "Até R$ 1.000 tem esse: R$ 599,90."
    assert unsupported_amounts(reply, ["violão até R$1000", '{"preco": "R$ 599,90"}']) == set()


def test_invented_amount_is_caught():
    assert unsupported_amounts("Fica R$ 499,90.", ['{"preco": "R$ 599,90"}']) == {Decimal("499.90")}


def test_plain_decimal_in_the_reply_is_compared_with_the_formatted_evidence():
    assert unsupported_amounts("Fica R$ 1199.80.", ['{"preco": "R$ 1.199,80"}']) == set()
