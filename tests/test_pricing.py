from decimal import Decimal

import pytest

from emporio.pricing import brl, max_installments, metro_shipping, quote


@pytest.mark.parametrize(
    "value, expected",
    [("2199", "R$ 2.199,00"), ("599.9", "R$ 599,90"), ("12000", "R$ 12.000,00"), ("0.5", "R$ 0,50")],
)
def test_brl_uses_brazilian_format(value, expected):
    assert brl(Decimal(value)) == expected


@pytest.mark.parametrize(
    "amount, expected",
    [
        ("90", 1),       # 2x would be R$ 45, under the R$ 50 floor
        ("159.90", 3),   # 3x = R$ 53,30
        ("240", 3),      # 4x = R$ 60, under the R$ 80 floor of the 4x-6x tier
        ("599.90", 6),   # 6x = R$ 99,98 passes; 7x needs R$ 100
        ("1000", 10),    # 10x is exactly the R$ 100 floor
        ("1199", 11),    # 12x = R$ 99,92 falls short
        ("2199", 12),
    ],
)
def test_installments_follow_section_3_1_tiers(amount, expected):
    assert max_installments(Decimal(amount)) == expected


def test_pix_takes_five_percent_off_list_price():
    assert quote(Decimal("2199")).pix_price == Decimal("2089.05")


def test_pix_does_not_stack_on_a_promotion():
    promo = quote(Decimal("549"), 20, "Desconto Exclusivo")
    assert promo.price == Decimal("439.20")
    assert promo.pix_price is None


def test_promotion_shows_original_price_and_percent():
    data = quote(Decimal("549"), 20, "Desconto Exclusivo").to_dict()
    assert data["preco_original"] == "R$ 549,00"
    assert data["desconto"] == "20%"
    assert data["preco_promocional"] == "R$ 439,20"


@pytest.mark.parametrize("subtotal, fee", [("499.99", "35"), ("500", "0"), ("500.01", "0")])
def test_metro_shipping(subtotal, fee):
    assert metro_shipping(Decimal(subtotal)) == Decimal(fee)
