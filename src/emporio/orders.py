"""Orders: identity check, customer-safe views and return-window rules."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from emporio.catalog import Catalog, read_csv
from emporio.pricing import brl

STATUS_LABELS = {
    "pending": "Aguardando confirmação do pagamento",
    "confirmed": "Pagamento confirmado, em separação",
    "shipped": "Enviado",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}
PAYMENT_LABELS = {"pix": "PIX", "boleto": "Boleto", "debit": "Cartão de débito"}
STALLED_AFTER_DAYS = 10
RETURN_WINDOW_DAYS = 7
DEFECT_EXCHANGE_DAYS = 30
LEGAL_WARRANTY_DAYS = 90


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
    date: date
    status: str
    total: Decimal
    payment_method: str
    tracking_code: str
    estimated_delivery: date | None
    notes: str
    items: tuple[tuple[int, int], ...]  # (product_id, quantity)


class OrderBook:
    def __init__(self, data_dir: Path, catalog: Catalog):
        self.catalog = catalog
        self.customers = {int(row["customer_id"]): row for row in read_csv(data_dir / "customers.csv")}
        items: dict[int, list[tuple[int, int]]] = {}
        for row in read_csv(data_dir / "order_items.csv"):
            items.setdefault(int(row["order_id"]), []).append((int(row["product_id"]), int(row["quantity"])))
        self.orders = {
            int(row["order_id"]): Order(
                id=int(row["order_id"]),
                customer_id=int(row["customer_id"]),
                date=parse_date(row["order_date"]),
                status=row["status"],
                total=Decimal(row["total_brl"]),
                payment_method=row["payment_method"],
                tracking_code=row["tracking_code"],
                estimated_delivery=parse_date(row["estimated_delivery"]),
                notes=row["notes"],
                items=tuple(items.get(int(row["order_id"]), ())),
            )
            for row in read_csv(data_dir / "orders.csv")
        }

    def verified_order(self, order_id: int, contact: str) -> Order | None:
        """Return the order only if the contact is the one on file for its customer."""
        order = self.orders.get(order_id)
        if order is None or not self._contact_matches(self.customers[order.customer_id], contact):
            return None
        return order

    @staticmethod
    def _contact_matches(customer: dict, contact: str) -> bool:
        contact = contact.strip().lower()
        if "@" in contact:
            return contact == customer["email"].lower()
        given, on_file = digits_of(contact).removeprefix("55"), digits_of(customer["phone"])
        return len(given) >= 8 and on_file.endswith(given)

    def view(self, order: Order, today: date) -> dict:
        """What may be said to the verified customer. No e-mail, phone or address."""
        customer = self.customers[order.customer_id]
        view = {
            "pedido": order.id,
            "cliente_primeiro_nome": customer["name"].split()[0],
            "data_do_pedido": format_date(order.date),
            "status": STATUS_LABELS[order.status],
            "total": brl(order.total),
            "pagamento": payment_label(order.payment_method),
            "itens": [
                {"produto": self.catalog.products[product_id].name, "quantidade": quantity}
                for product_id, quantity in order.items
            ],
        }
        if order.tracking_code:
            view["codigo_de_rastreio"] = order.tracking_code
        if order.estimated_delivery:
            view["previsao_de_entrega"] = format_date(order.estimated_delivery)
        if order.notes:
            view["observacao"] = order.notes
        view |= self._alerts(order, today)
        return view

    def _alerts(self, order: Order, today: date) -> dict:
        if order.status == "shipped" and order.estimated_delivery and today > order.estimated_delivery:
            return {"alerta": f"Entrega atrasada em {(today - order.estimated_delivery).days} dias."}
        idle_days = (today - order.date).days
        if order.status in ("pending", "confirmed") and idle_days > STALLED_AFTER_DAYS:
            return {"alerta": f"Pedido sem movimentação há {idle_days} dias."}
        return {}

    def return_decision(self, order: Order, reason: str, today: date) -> dict:
        """Apply manual section 4 with exact date arithmetic, so the model never counts days."""
        if order.status == "cancelled":
            return _decision(False, "O pedido já está cancelado, não há o que devolver.", "encaminhar_equipe")
        if order.status in ("pending", "confirmed"):
            return _decision(
                False,
                "O pedido ainda não foi enviado e o manual não define regra de cancelamento antes do envio.",
                "encaminhar_equipe",
            )
        if order.status == "shipped":
            return _decision(
                False,
                "O pedido ainda não foi recebido. Os prazos de devolução contam a partir do recebimento.",
                "aguardar_recebimento",
            )
        # The data has no real delivery date, so the estimated one stands in for it.
        received = order.estimated_delivery
        days_since_receipt = (today - received).days
        facts = {
            "data_de_recebimento_considerada": format_date(received),
            "dias_desde_o_recebimento": days_since_receipt,
            "dias_desde_a_compra": (today - order.date).days,
        }
        if reason == "defeito":
            return self._defect_decision(order, today, days_since_receipt) | facts
        section = "4.1" if reason == "arrependimento" else "4.3"
        if days_since_receipt <= RETURN_WINDOW_DAYS:
            return (
                _decision(True, f"Dentro do prazo de {RETURN_WINDOW_DAYS} dias.", "seguir_condicoes", section)
                | facts
            )
        return (
            _decision(False, f"Fora do prazo de {RETURN_WINDOW_DAYS} dias.", "informar_cliente", section)
            | facts
        )

    @staticmethod
    def _defect_decision(order: Order, today: date, days_since_receipt: int) -> dict:
        if (today - order.date).days <= DEFECT_EXCHANGE_DAYS:
            return _decision(True, "Dentro dos 30 dias de troca por defeito.", "seguir_condicoes", "4.2")
        if days_since_receipt <= LEGAL_WARRANTY_DAYS:
            return _decision(
                True,
                "Passou dos 30 dias de troca direta, mas está na garantia legal de 90 dias.",
                "encaminhar_equipe",
                "8.1",
            )
        return _decision(
            False,
            "Fora da troca direta e da garantia legal. "
            "Pode valer a garantia do fabricante, e a loja pode intermediar.",
            "oferecer_intermediacao",
            "4.2 e 8.2",
        )


def _decision(eligible: bool, reason: str, next_step: str, section: str | None = None) -> dict:
    decision = {"elegivel": eligible, "motivo": reason, "proximo_passo": next_step}
    if section:
        decision["secao_do_manual"] = section
    return decision
