"""Orders: phone identity check and customer-safe views."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from emporio.catalog import Catalog, read_csv
from emporio.pricing import brl

STATUS_LABELS = {
    "pending": "Pendente",
    "confirmed": "Confirmado",
    "shipped": "Enviado",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}
PAYMENT_LABELS = {"pix": "PIX", "boleto": "Boleto", "debit": "Cartão de débito"}
STALLED_AFTER_DAYS = 15

Day = date  # the Order.date field shadows the type inside the class body


def payment_label(method: str) -> str:
    if method.startswith("credit_"):
        return f"Cartão de crédito em {method.removeprefix('credit_')}"
    return PAYMENT_LABELS.get(method, method)


def parse_date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


def format_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def digits_of(text: str) -> str:
    return re.sub(r"\D", "", text)


@dataclass(frozen=True)
class Order:
    id: int
    customer_id: int
    date: Day
    status: str
    total: Decimal
    payment_method: str
    tracking_code: str
    estimated_delivery: Day | None
    notes: str
    items: tuple[tuple[int, int], ...]  # (product_id, quantity)


class OrderBook:
    def __init__(self, data_dir: Path, catalog: Catalog):
        self.catalog = catalog
        self.customers: dict[int, dict[str, str]] = dict(
            read_csv(
                data_dir / "customers.csv",
                ("customer_id", "name", "phone"),
                lambda row: (int(row["customer_id"]), dict(row)),
            )
        )
        items: dict[int, list[tuple[int, int]]] = {}
        item_rows = read_csv(
            data_dir / "order_items.csv",
            ("order_id", "product_id", "quantity"),
            lambda row: (int(row["order_id"]), int(row["product_id"]), int(row["quantity"])),
        )
        for order_id, product_id, quantity in item_rows:
            items.setdefault(order_id, []).append((product_id, quantity))
        order_columns = (
            "order_id",
            "customer_id",
            "order_date",
            "status",
            "total_brl",
            "payment_method",
            "tracking_code",
            "estimated_delivery",
            "notes",
        )
        self.orders: dict[int, Order] = {
            order.id: order
            for order in read_csv(
                data_dir / "orders.csv", order_columns, lambda row: self._build_order(row, items)
            )
        }

    @staticmethod
    def _build_order(row: dict[str, str], items: dict[int, list[tuple[int, int]]]) -> Order:
        order_id = int(row["order_id"])
        return Order(
            id=order_id,
            customer_id=int(row["customer_id"]),
            date=date.fromisoformat(row["order_date"]),
            status=row["status"],
            total=Decimal(row["total_brl"]),
            payment_method=row["payment_method"],
            tracking_code=row["tracking_code"],
            estimated_delivery=parse_date(row["estimated_delivery"]),
            notes=row["notes"],
            items=tuple(items.get(order_id, ())),
        )

    def verified_order(self, order_id: int, phone: str) -> Order | None:
        """Return the order only if the phone is the one on file for its customer.

        E-mail never identifies anyone, and a partial number is refused.
        """
        order = self.orders.get(order_id)
        if order is None or not _phone_matches(self.customers[order.customer_id]["phone"], phone):
            return None
        return order

    def view(self, order: Order, today: date) -> dict[str, Any]:
        """What may be said to the verified customer. No e-mail, phone or address."""
        customer = self.customers[order.customer_id]
        view = {
            "pedido": order.id,
            "cliente_primeiro_nome": customer["name"].split()[0],
            "data_do_pedido": format_date(order.date),
            "status": STATUS_LABELS[order.status],
            "valor_registrado": brl(order.total),
            "pagamento": payment_label(order.payment_method),
            "itens": [
                {"produto": self.catalog.products[product_id].name, "quantidade": quantity}
                for product_id, quantity in order.items
            ],
            "dias_desde_a_compra": (today - order.date).days,
            "requer_atencao": _needs_attention(order, today),
        }
        if order.tracking_code:
            view["codigo_de_rastreio"] = order.tracking_code
        if order.estimated_delivery:
            view["previsao_de_entrega"] = format_date(order.estimated_delivery)
            view["dias_desde_a_previsao"] = (today - order.estimated_delivery).days
        if order.status == "cancelled" and order.notes:
            view["motivo_cancelamento"] = order.notes
        return view


def _phone_matches(on_file: str, given: str) -> bool:
    """Accept the full number in any format, with or without 0, +55 or the area code."""
    digits = digits_of(given).removeprefix("0")
    if len(digits) == 13:
        digits = digits.removeprefix("55")
    full = digits_of(on_file)
    return digits in (full, full[-9:])


def _needs_attention(order: Order, today: date) -> bool:
    """Shipped past its estimate, or pending/confirmed for more than 15 calendar days."""
    if order.status == "shipped":
        return order.estimated_delivery is not None and today > order.estimated_delivery
    if order.status in ("pending", "confirmed"):
        return (today - order.date).days > STALLED_AFTER_DAYS
    return False
