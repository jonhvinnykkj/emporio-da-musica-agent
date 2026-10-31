"""Product catalog: loads the CSVs, resolves contradictions and answers searches."""

import csv
import difflib
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from emporio.pricing import Quote, quote

AVAILABLE, OUT_OF_STOCK, DISCONTINUED, COMING_SOON = (
    "disponivel",
    "fora_de_estoque",
    "descontinuado",
    "em_breve",
)
# Names that identify a maker or model line. A description citing one that is absent
# from the product name describes a different instrument (e.g. "Music Man Bass 1X"
# described as a Fender Jazz Bass), so the name and the structured specs win.
KNOWN_MARKS = (
    "Crafter",
    "Fender",
    "Giannini",
    "Gibson",
    "Ibanez",
    "Kala",
    "Kalani",
    "Korg",
    "Martin",
    "Music Man",
    "Nord",
    "Ohana",
    "Pearl",
    "Precision",
    "PRS",
    "Roland",
    "Rozini",
    "Shelby",
    "Tagima",
    "Takamine",
    "Tama",
    "Taylor",
    "Yamaha",
)
CATEGORY_WORDS = {
    "guitarra": 1,
    "guitarras": 1,
    "baixo": 2,
    "baixos": 2,
    "contrabaixo": 2,
    "bateria": 3,
    "baterias": 3,
    "percussao": 3,
    "teclado": 4,
    "teclados": 4,
    "piano": 4,
    "pianos": 4,
    "sintetizador": 4,
    "violao": 5,
    "violoes": 5,
    "flauta": 6,
    "clarinete": 6,
    "saxofone": 6,
    "sax": 6,
    "oboe": 6,
    "trompete": 7,
    "trombone": 7,
    "tuba": 7,
    "trompa": 7,
    "violino": 8,
    "viola": 8,
    "violoncelo": 8,
    "ukulele": 9,
    "ukuleles": 9,
}
STOPWORDS = {"a", "as", "com", "da", "de", "do", "e", "em", "na", "no", "o", "os", "para", "por", "um", "uma"}
FUZZY_CUTOFF = 0.8


def normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip()


def description_contradicts_name(name: str, description: str) -> bool:
    cited = [mark for mark in KNOWN_MARKS if re.search(rf"\b{mark}\b", description, re.IGNORECASE)]
    return bool(cited) and not any(mark.lower() in name.lower() for mark in cited)


class DataError(Exception):
    """A store data file is missing, lacks a column or holds a value that cannot be read."""


def read_csv[T](path: Path, columns: tuple[str, ...], build: Callable[[dict[str, str]], T]) -> list[T]:
    """Read one CSV and build an item per row; every failure names the file."""
    try:
        with path.open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            missing = [column for column in columns if column not in (reader.fieldnames or [])]
            if missing:
                raise DataError(f"{path.name}: missing column(s) {', '.join(missing)}")
            return [build(row) for row in reader]
    except FileNotFoundError:
        raise DataError(f"{path.name}: file not found in {path.parent}") from None
    except (KeyError, ValueError, InvalidOperation, TypeError) as error:
        raise DataError(f"{path.name}: invalid value ({error!r})") from error


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    category_id: int
    category: str
    list_price: Decimal
    description: str
    stock: int
    status: str
    specs: dict[str, Any]
    quote: Quote
    search_tokens: frozenset[str] = field(repr=False, default=frozenset())
    search_compact: str = field(repr=False, default="")

    @property
    def description_reliable(self) -> bool:
        return not description_contradicts_name(self.name, self.description)

    @property
    def availability(self) -> str:
        """Status wins over stock: a discontinued or unreleased item is never for sale."""
        if self.status == "discontinued":
            return DISCONTINUED
        if self.status == "coming_soon":
            return COMING_SOON
        return AVAILABLE if self.stock > 0 else OUT_OF_STOCK

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "nome": self.name,
            "categoria": self.category,
            "disponibilidade": self.availability,
            "promocao_ativa": self.quote.has_promotion,
        }
        if self.availability == AVAILABLE:
            data["estoque"] = self.stock
            data |= self.quote.to_dict()
        if self.description_reliable:
            data["descricao"] = self.description
            data["especificacoes"] = self.specs
        else:
            data["nota_interna"] = "Descrição do cadastro diverge do nome. Use só nome e especificações."
        return data


class Catalog:
    def __init__(self, data_dir: Path):
        self.categories: dict[int, str] = dict(
            read_csv(
                data_dir / "categories.csv",
                ("category_id", "name"),
                lambda row: (int(row["category_id"]), row["name"]),
            )
        )
        # Only rows with is_active=1 are promotions; the biggest discount wins per product.
        self.active_promotions: dict[int, dict[str, Any]] = {}
        promotions = read_csv(
            data_dir / "promotions.csv",
            ("product_id", "discount_percent", "description", "is_active"),
            lambda row: (
                int(row["product_id"]),
                {"name": row["description"], "percent": int(row["discount_percent"])},
                row["is_active"] == "1",
            ),
        )
        for product_id, promotion, is_active in promotions:
            current = self.active_promotions.get(product_id)
            if is_active and (current is None or promotion["percent"] > current["percent"]):
                self.active_promotions[product_id] = promotion

        self.products: dict[int, Product] = {}
        product_columns = (
            "product_id",
            "category_id",
            "name",
            "price_brl",
            "description",
            "stock_quantity",
            "status",
            "specs",
        )
        for product in read_csv(data_dir / "products.csv", product_columns, self._build_product):
            self.products[product.id] = product

    def _build_product(self, row: dict[str, str]) -> Product:
        product_id = int(row["product_id"])
        category_id = int(row["category_id"])
        list_price = Decimal(row["price_brl"])
        promotion = self.active_promotions.get(product_id)
        price = quote(list_price, promotion["percent"], promotion["name"]) if promotion else quote(list_price)
        specs = json.loads(row["specs"])
        draft = Product(
            id=product_id,
            name=row["name"],
            category_id=category_id,
            category=self.categories[category_id],
            list_price=list_price,
            description=row["description"],
            stock=int(row["stock_quantity"]),
            status=row["status"],
            specs=specs,
            quote=price,
        )
        searchable = [draft.name, draft.category, *map(str, specs.values())]
        if draft.description_reliable:
            searchable.append(draft.description)
        text = normalize(" ".join(searchable))
        return Product(
            **{
                **draft.__dict__,
                "search_tokens": frozenset(text.split()),
                "search_compact": text.replace(" ", ""),
            }
        )

    def in_category(self, category_id: int) -> list[Product]:
        return [p for p in self.products.values() if p.category_id == category_id]

    def overview(self) -> str:
        """One line per category with how many items are for sale, used in the system prompt."""
        lines = []
        for category_id, name in self.categories.items():
            count = sum(p.availability == AVAILABLE for p in self.in_category(category_id))
            lines.append(
                f"- {name}: {count} modelos à venda" if count else f"- {name}: nenhum item no momento"
            )
        return "\n".join(lines)

    def search(
        self,
        query: str | None = None,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        strings: str | None = None,
        electronics: bool | None = None,
        on_sale: bool = False,
        limit: int = 5,
    ) -> dict[str, Any]:
        tokens = [t for t in normalize(query or "").split() if t not in STOPWORDS]
        category_id = next((i for i, name in self.categories.items() if name == category), None)
        for token in list(tokens):
            if token in CATEGORY_WORDS:
                category_id = category_id or CATEGORY_WORDS[token]
                tokens.remove(token)

        candidates = [
            p
            for p in self.products.values()
            if (category_id is None or p.category_id == category_id)
            and _matches_specs(p, strings, electronics)
            and (not on_sale or p.quote.has_promotion)
        ]
        match_quality, matched = _rank(candidates, tokens)
        minimum, maximum = _bound(min_price), _bound(max_price)
        available = [p for p in matched if p.availability == AVAILABLE and _in_range(p, minimum, maximum)]
        available.sort(key=lambda p: p.quote.price)

        result: dict[str, Any] = {
            "total_encontrado": len(available),
            "mostrando": min(len(available), limit),
            "produtos": [p.to_dict() for p in available[:limit]],
        }
        if tokens:
            result["correspondencia"] = match_quality
            unavailable = [p for p in matched if p.availability != AVAILABLE]
            if unavailable:
                result["indisponiveis"] = [p.to_dict() for p in unavailable[:limit]]
                result["alternativas"] = [p.to_dict() for p in self.alternatives(unavailable[0])]
        if category_id and not self.in_category(category_id):
            result["categoria_sem_produtos"] = True
        return result

    def alternatives(self, product: Product, count: int = 3) -> list[Product]:
        """Closest items for sale: same category, same string type when there is one, nearest price."""
        pool = [p for p in self.in_category(product.category_id) if p.availability == AVAILABLE]
        same_strings = [p for p in pool if p.specs.get("strings") == product.specs.get("strings")]
        return sorted(same_strings or pool, key=lambda p: abs(p.list_price - product.list_price))[:count]


def _matches_specs(product: Product, strings: str | None, electronics: bool | None) -> bool:
    if strings and product.specs.get("strings") != {"nylon": "nylon", "aco": "steel"}.get(strings):
        return False
    if electronics is not None and product.specs.get("electronics") != ("yes" if electronics else "no"):
        return False
    return True


def _bound(value: float | None) -> Decimal | None:
    """A price limit as Decimal; anything that is not a finite-or-infinite number is a bad argument."""
    if value is None:
        return None
    try:
        bound = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"invalid price limit: {value!r}") from None
    if bound.is_nan():
        raise ValueError(f"invalid price limit: {value!r}")
    return bound


def _in_range(product: Product, minimum: Decimal | None, maximum: Decimal | None) -> bool:
    """Compares against what the customer pays today, so a promotion can bring an item into range."""
    price = product.quote.price
    return (minimum is None or price >= minimum) and (maximum is None or price <= maximum)


def _token_hits(product: Product, token: str) -> bool:
    if token in product.search_tokens or (len(token) >= 4 and token in product.search_compact):
        return True
    return bool(difflib.get_close_matches(token, product.search_tokens, n=1, cutoff=FUZZY_CUTOFF))


def _rank(products: list[Product], tokens: list[str]) -> tuple[str, list[Product]]:
    """Keep the products matching the most query tokens and say how good that match was."""
    if not tokens:
        return "todos", products
    joined = "".join(tokens)
    scored = [
        (len(tokens) if joined in p.search_compact else sum(_token_hits(p, t) for t in tokens), p)
        for p in products
    ]
    best = max((score for score, _ in scored), default=0)
    if best == 0:
        return "nenhuma", []
    quality = "exata" if best == len(tokens) else "parcial"
    return quality, [p for score, p in scored if score == best]
