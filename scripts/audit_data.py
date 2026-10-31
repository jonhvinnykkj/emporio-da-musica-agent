"""Print the contradictions found in the store data: uv run python scripts/audit_data.py"""

from collections import Counter
from decimal import Decimal
from pathlib import Path

from emporio.catalog import AVAILABLE, Catalog
from emporio.orders import OrderBook
from emporio.pricing import max_installments

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    catalog = Catalog(DATA_DIR)
    book = OrderBook(DATA_DIR, catalog)
    products = catalog.products.values()

    print("Products whose status contradicts stock:")
    for p in products:
        if (p.status != "active" and p.stock > 0) or (p.status == "active" and p.stock == 0):
            print(f"  {p.id} {p.name}: status={p.status}, stock={p.stock}")

    print("Descriptions that name another brand:")
    for p in products:
        if not p.description_reliable:
            print(f"  {p.id} {p.name}: {p.description[:60]}")

    print("Categories with nothing for sale:")
    for category_id, name in catalog.categories.items():
        if not any(p.availability == AVAILABLE for p in catalog.in_category(category_id)):
            print(f"  {name}")

    print("Orders whose total differs from their items at list price:")
    for order in book.orders.values():
        computed = sum(catalog.products[pid].list_price * qty for pid, qty in order.items)
        if computed != order.total:
            print(f"  order {order.id}: total={order.total}, items={computed}")

    print("Orders paid by PIX without the 5% discount:")
    print(" ", [o.id for o in book.orders.values() if o.payment_method == "pix" and o.total == sum(
        catalog.products[pid].list_price * qty for pid, qty in o.items)])

    print("Orders above the installment limit of section 3.1:")
    for order in book.orders.values():
        if order.payment_method.startswith("credit_"):
            count = int(order.payment_method.removeprefix("credit_").removesuffix("x"))
            if count > max_installments(Decimal(order.total)):
                print(f"  order {order.id}: {count}x on {order.total}")

    print("Orders containing items not for sale today:")
    for order in book.orders.values():
        for pid, _ in order.items:
            if catalog.products[pid].status != "active":
                print(f"  order {order.id}: {catalog.products[pid].name} ({catalog.products[pid].status})")

    print("E-mails shared by two customer records:")
    emails = Counter(c["email"] for c in book.customers.values())
    print(" ", [email for email, count in emails.items() if count > 1])

    print("Products with more than one promotion row:")
    print(" ", [pid for pid, rows in catalog.expired_promotions.items() if len(rows) > 1])


if __name__ == "__main__":
    main()
