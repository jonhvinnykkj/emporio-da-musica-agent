"""Product catalog: loads the CSVs, resolves contradictions and answers searches."""

import csv
import difflib
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

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
    "Crafter", "Fender", "Giannini", "Gibson", "Ibanez", "Kala", "Kalani", "Korg", "Martin",
    "Music Man", "Nord", "Ohana", "Pearl", "Precision", "PRS", "Roland", "Rozini", "Shelby",
    "Tagima", "Takamine", "Tama", "Taylor", "Yamaha",
)
CATEGORY_WORDS = {
    "guitarra": 1, "guitarras": 1,
    "baixo": 2, "baixos": 2, "contrabaixo": 2,
    "bateria": 3, "baterias": 3, "percussao": 3,
    "teclado": 4, "teclados": 4, "piano": 4, "pianos": 4, "sintetizador": 4,
    "violao": 5, "violoes": 5,
    "flauta": 6, "clarinete": 6, "saxofone": 6, "sax": 6, "oboe": 6,
    "trompete": 7, "trombone": 7, "tuba": 7, "trompa": 7,
    "violino": 8, "viola": 8, "violoncelo": 8,
    "ukulele": 9, "ukuleles": 9,
}
STOPWORDS = {"a", "as", "com", "da", "de", "do", "e", "em", "na", "no", "o", "os", "para", "por", "um", "uma"}
FUZZY_CUTOFF = 0.8


def normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip()


def description_contradicts_name(name: str, description: str) -> bool:
    cited = [mark for mark in KNOWN_MARKS if re.search(rf"\b{mark}\b", description, re.IGNORECASE)]
    return bool(cited) and not any(mark.lower() in name.lower() for mark in cited)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


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
    specs: dict
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

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "nome": self.name,
            "categoria": self.category,
            "disponibilidade": self.availability,
            "especificacoes": self.specs,
        }
        if self.availability == AVAILABLE:
            data["estoque"] = self.stock
            data |= self.quote.to_dict()
        if self.description_reliable:
            data["descricao"] = self.description
        else:
            data["nota_interna"] = "Descrição do cadastro diverge do nome. Use só nome e especificações."
        return data


class Catalog:
    def __init__(self, data_dir: Path):
        categories = {int(row["category_id"]): row["name"] for row in read_csv(data_dir / "categories.csv")}
        self.categories = categories
        self.active_promotions: dict[int, dict] = {}
        self.expired_promotions: dict[int, list[dict]] = defaultdict(list)
        for row in read_csv(data_dir / "promotions.csv"):
            promotion = {"name": row["description"], "percent": int(row["discount_percent"])}
            product_id = int(row["product_id"])
            current = self.active_promotions.get(product_id)
            if row["is_active"] != "1":
                self.expired_promotions[product_id].append(promotion)
            elif current is None or promotion["percent"] > current["percent"]:
                self.active_promotions[product_id] = promotion

        self.products: dict[int, Product] = {}
        for row in read_csv(data_dir / "products.csv"):
            product = self._build_product(row)
            self.products[product.id] = product

    def _build_product(self, row: dict) -> Product:
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
            **{**draft.__dict__, "search_tokens": frozenset(text.split()), "search_compact": text.replace(" ", "")}
        )

    def in_category(self, category_id: int) -> list[Product]:
        return [p for p in self.products.values() if p.category_id == category_id]

    def overview(self) -> str:
        """One line per category with how many items are for sale, used in the system prompt."""
        lines = []
        for category_id, name in self.categories.items():
            count = sum(p.availability == AVAILABLE for p in self.in_category(category_id))
            lines.append(f"- {name}: {count} modelos à venda" if count else f"- {name}: nenhum item no momento")
        return "\n".join(lines)

    def search(
        self,
        query: str | None = None,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        strings: str | None = None,
        electronics: bool | None = None,
        limit: int = 8,
    ) -> dict:
        tokens = [t for t in normalize(query or "").split() if t not in STOPWORDS]
        category_id = next((i for i, name in self.categories.items() if name == category), None)
        for token in list(tokens):
            if token in CATEGORY_WORDS:
                category_id = category_id or CATEGORY_WORDS[token]
                tokens.remove(token)

        candidates = [
            p for p in self.products.values()
            if (category_id is None or p.category_id == category_id)
            and _matches_specs(p, strings, electronics)
        ]
        match_quality, matched = _rank(candidates, tokens)
        available = [p for p in matched if p.availability == AVAILABLE and _in_range(p, min_price, max_price)]
        available.sort(key=lambda p: p.quote.price)

        result = {
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

    def promotions_report(self, query: str | None = None) -> dict:
        wanted = normalize(query or "")
        active = []
        for product_id, promotion in self.active_promotions.items():
            product = self.products[product_id]
            if product.availability != AVAILABLE:
                continue
            if not wanted or wanted in normalize(f"{promotion['name']} {product.name}"):
                active.append(product.to_dict())
        expired = sorted({
            promotion["name"]
            for promotions in self.expired_promotions.values()
            for promotion in promotions
            if wanted and wanted in normalize(promotion["name"])
        })
        return {"promocoes_ativas": active, "campanhas_encerradas": expired}


def _matches_specs(product: Product, strings: str | None, electronics: bool | None) -> bool:
    if strings and product.specs.get("strings") != {"nylon": "nylon", "aco": "steel"}.get(strings):
        return False
    if electronics is not None and product.specs.get("electronics") != ("yes" if electronics else "no"):
        return False
    return True


def _in_range(product: Product, min_price: float | None, max_price: float | None) -> bool:
    """Compares against what the customer pays today, so a promotion can bring an item into range."""
    price = product.quote.price
    return (min_price is None or price >= Decimal(str(min_price))) and (
        max_price is None or price <= Decimal(str(max_price))
    )


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
