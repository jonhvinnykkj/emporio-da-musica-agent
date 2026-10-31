from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from emporio.pricing import (
    INSTALLMENT_TIERS,
    brl,
    installment_text,
    max_installments,
    metro_shipping,
    quote,
    to_money,
)


@pytest.mark.parametrize(
    "value, expected",
    [("2199", "R$ 2.199,00"), ("599.9", "R$ 599,90"), ("12000", "R$ 12.000,00"), ("0.5", "R$ 0,50")],
)
def test_brl_uses_brazilian_format(value, expected):
    assert brl(Decimal(value)) == expected


@pytest.mark.parametrize(
    "amount, expected",
    [
        ("90", 1),  # 2x would be R$ 45, under the R$ 50 floor
        ("159.90", 3),  # 3x = R$ 53,30
        ("240", 3),  # 4x = R$ 60, under the R$ 80 floor of the 4x-6x tier
        ("599.90", 6),  # 6x = R$ 99,98 passes; 7x needs R$ 100
        ("1000", 10),  # 10x is exactly the R$ 100 floor
        ("1199", 11),  # 12x = R$ 99,92 falls short
        ("2199", 12),
    ],
)
def test_installments_follow_section_3_1_tiers(amount, expected):
    assert max_installments(Decimal(amount)) == expected


def test_pix_takes_five_percent_off_list_price():
    assert quote(Decimal("2199")).to_dict()["preco_no_pix"] == "R$ 2.089,05"


def test_pix_does_not_stack_on_a_promotion():
    promo = quote(Decimal("549"), 20, "Desconto Exclusivo")
    assert promo.price == Decimal("439.20")
    assert "preco_no_pix" not in promo.to_dict()
    assert promo.pix_total(1) == Decimal("439.20")


def test_promotion_shows_original_price_and_percent():
    data = quote(Decimal("549"), 20, "Desconto Exclusivo").to_dict()
    assert data["preco_original"] == "R$ 549,00"
    assert data["desconto"] == "20%"
    assert data["preco_promocional"] == "R$ 439,20"


@pytest.mark.parametrize("subtotal, fee", [("499.99", "35"), ("500", "0"), ("500.01", "0")])
def test_metro_shipping(subtotal, fee):
    assert metro_shipping(Decimal(subtotal)) == Decimal(fee)


@given(st.decimals(min_value="0.01", max_value="100000", places=2))
def test_installment_never_goes_below_the_floor(amount):
    count = max_installments(amount)
    floor = next(value for limit, value in INSTALLMENT_TIERS if count <= limit)
    assert count == 1 or amount / count >= floor


@pytest.mark.parametrize(
    "value, expected", [("0.125", "0.13"), ("2.675", "2.68"), ("2.665", "2.67"), ("10.004", "10.00")]
)
def test_to_money_rounds_half_up(value, expected):
    assert to_money(value) == Decimal(expected)


@pytest.mark.parametrize(
    "amount, expected",
    [("49.99", 1), ("100", 2), ("99.99", 1), ("150", 3), ("319.99", 3), ("320", 4), ("480", 6), ("600", 6)],
)
def test_installment_boundaries(amount, expected):
    assert max_installments(Decimal(amount)) == expected


def test_installment_text_states_count_and_value():
    assert installment_text(Decimal("2199")) == "até 12x de R$ 183,25 sem juros"
    assert installment_text(Decimal("120")) == "até 2x de R$ 60,00 sem juros"


def test_installment_text_says_cash_only_when_it_cannot_be_split():
    assert installment_text(Decimal("90")) == "à vista (R$ 90,00), valor não permite parcelar"


def test_quote_without_discount_keeps_the_list_price_and_no_promotion():
    plain = quote(Decimal("2199"))
    assert plain.list_price == plain.price == Decimal("2199") and not plain.has_promotion


def test_plain_quote_dict_has_price_pix_and_installments():
    assert quote(Decimal("2199")).to_dict() == {
        "preco": "R$ 2.199,00",
        "preco_no_pix": "R$ 2.089,05",
        "parcelamento": "até 12x de R$ 183,25 sem juros",
    }


def test_promotional_quote_dict_names_the_promotion_and_denies_pix():
    assert quote(Decimal("549"), 20, "Desconto Exclusivo").to_dict() == {
        "preco_original": "R$ 549,00",
        "desconto": "20%",
        "promocao": "Desconto Exclusivo",
        "preco_promocional": "R$ 439,20",
        "pix": "desconto de PIX não se aplica sobre preço promocional",
        "parcelamento": "até 5x de R$ 87,84 sem juros",
    }
