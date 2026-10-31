"""Contradictions found in the store data, one line per finding."""

from collections import Counter
from decimal import Decimal

from emporio.catalog import AVAILABLE, Catalog
from emporio.orders import OrderBook
from emporio.pricing import max_installments


def find_inconsistencies(catalog: Catalog, book: OrderBook) -> list[str]:
    findings = []
    for p in catalog.products.values():
        if (p.status != "active" and p.stock > 0) or (p.status == "active" and p.stock == 0):
            findings.append(f"produto {p.id} {p.name}: status {p.status} e estoque {p.stock}")
        if not p.description_reliable:
            findings.append(f"produto {p.id} {p.name}: a descrição cita outra marca")

    for category_id, name in catalog.categories.items():
        if not any(p.availability == AVAILABLE for p in catalog.in_category(category_id)):
            findings.append(f"categoria sem item à venda: {name}")

    for order in book.orders.values():
        at_list_price = sum(catalog.products[pid].list_price * qty for pid, qty in order.items)
        if at_list_price != order.total:
            findings.append(
                f"pedido {order.id}: total {order.total} difere dos itens a preço de tabela {at_list_price}"
            )
        if order.payment_method == "pix" and order.total == at_list_price:
            findings.append(f"pedido {order.id}: pago em PIX sem o desconto de 5%")
        if order.payment_method.startswith("credit_"):
            count = int(order.payment_method.removeprefix("credit_").removesuffix("x"))
            if count > max_installments(Decimal(order.total)):
                findings.append(f"pedido {order.id}: {count}x em {order.total} passa o limite da seção 3.1")
        for pid, _ in order.items:
            product = catalog.products[pid]
            if product.status != "active":
                findings.append(f"pedido {order.id}: contém {product.name}, que está {product.status}")

    emails = Counter(customer["email"] for customer in book.customers.values())
    findings.extend(
        f"e-mail {email} repetido em {count} clientes" for email, count in emails.items() if count > 1
    )
    return findings
