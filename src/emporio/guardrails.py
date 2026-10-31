"""Deterministic check: every amount in a reply must come from this turn's tools or the customer."""

import re
from decimal import Decimal

MONEY = re.compile(r"R\$\s*(\d[\d.]*(?:,\d{1,2})?)|(?<![\d.,/])(\d{1,3}(?:\.\d{3})*,\d{2})(?!\d)")


def amounts_in(text: str) -> set[Decimal]:
    amounts = set()
    for prefixed, bare in MONEY.findall(text):
        digits = (prefixed or bare).rstrip(".").replace(".", "").replace(",", ".")
        amounts.add(Decimal(digits))
    return amounts


def unsupported_amounts(reply: str, evidence: list[str]) -> set[Decimal]:
    return amounts_in(reply) - set().union(*map(amounts_in, evidence))
