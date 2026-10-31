"""Deterministic check: every R$ amount in a reply must come from this turn's tools, manual or customer."""

import re
from decimal import Decimal

# Only values written with the R$ prefix count: "12x de 183,25" or "7 dias" are not read as money.
MONEY = re.compile(r"R\$\s*(\d+(?:\.\d+)*(?:,\d{1,2})?)")
DOT_DECIMAL = re.compile(r"(\d+(?:\.\d+)*)\.(\d{2})")


def _parse(token: str) -> Decimal:
    """With a comma, dots are thousands separators. Without one, a final dot plus 2 digits is a decimal."""
    if "," in token:
        return Decimal(token.replace(".", "").replace(",", "."))
    decimal = DOT_DECIMAL.fullmatch(token)
    if decimal:
        return Decimal(decimal.group(1).replace(".", "") + "." + decimal.group(2))
    return Decimal(token.replace(".", ""))


def amounts_in(text: str) -> set[Decimal]:
    return {_parse(token) for token in MONEY.findall(text)}


def unsupported_amounts(reply: str, evidence: list[str]) -> set[Decimal]:
    return amounts_in(reply) - set().union(*map(amounts_in, evidence))
