"""Money rules from the store manual. Every amount a customer sees is computed here."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
PIX_DISCOUNT = Decimal("0.05")
MAX_INSTALLMENTS = 12
# (highest number of installments, minimum installment value) - manual section 3.1
INSTALLMENT_TIERS = ((3, Decimal("50")), (6, Decimal("80")), (12, Decimal("100")))
METRO_FREE_SHIPPING_FROM = Decimal("500")
METRO_SHIPPING_FEE = Decimal("35")


def to_money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def brl(value: Decimal) -> str:
    """Format as Brazilian currency: Decimal('2199') -> 'R$ 2.199,00'."""
    text = f"{to_money(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {text}"


def max_installments(amount: Decimal) -> int:
    """Highest number of interest-free installments allowed for an amount."""
    best = 1
    for count in range(2, MAX_INSTALLMENTS + 1):
        minimum = next(value for limit, value in INSTALLMENT_TIERS if count <= limit)
        if amount / count >= minimum:
            best = count
    return best


def installment_text(amount: Decimal) -> str:
    count = max_installments(amount)
    if count == 1:
        return f"à vista ({brl(amount)}), valor não permite parcelar"
    return f"até {count}x de {brl(amount / count)} sem juros"


@dataclass(frozen=True)
class Quote:
    list_price: Decimal
    price: Decimal
    discount_percent: int | None = None
    promotion: str | None = None

    @property
    def has_promotion(self) -> bool:
        return self.promotion is not None

    @property
    def pix_price(self) -> Decimal | None:
        """PIX discount does not stack on promotional prices (manual section 6.2)."""
        return None if self.has_promotion else to_money(self.price * (1 - PIX_DISCOUNT))

    def to_dict(self) -> dict:
        if self.has_promotion:
            return {
                "preco_original": brl(self.list_price),
                "desconto": f"{self.discount_percent}%",
                "promocao": self.promotion,
                "preco_promocional": brl(self.price),
                "pix": "desconto de PIX não se aplica sobre preço promocional",
                "parcelamento": installment_text(self.price),
            }
        return {
            "preco": brl(self.price),
            "preco_no_pix": brl(self.pix_price),
            "parcelamento": installment_text(self.price),
        }


def quote(list_price: Decimal, discount_percent: int | None = None, promotion: str | None = None) -> Quote:
    if discount_percent is None:
        return Quote(list_price=list_price, price=list_price)
    price = to_money(list_price * (100 - discount_percent) / 100)
    return Quote(list_price, price, discount_percent, promotion)


def metro_shipping(subtotal: Decimal) -> Decimal:
    """Flat metro delivery fee. The manual leaves exactly R$ 500 undefined; we treat it as free."""
    return Decimal("0") if subtotal >= METRO_FREE_SHIPPING_FROM else METRO_SHIPPING_FEE
