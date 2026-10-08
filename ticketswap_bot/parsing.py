"""Pure helpers to interpret TicketSwap listing cards (no browser needed)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# "€ 45,50", "€45.50", "45,50 €", "£1,234.00", "EUR 30"
_PRICE_RE = re.compile(
    r"(?:[€£$]|EUR|GBP|USD|CHF|DKK|SEK|NOK|PLN)\s*(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    r"|(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?:[€£$]|EUR|GBP|USD|CHF)",
    re.IGNORECASE,
)

_QTY_RE = re.compile(
    r"(\d+)\s*(?:x\s*)?(?:tickets?|biglietti|biglietto|kaarten|kaart|tickets?|billets?|entradas?|karten)\b",
    re.IGNORECASE,
)

_SOLD_WORDS = ("sold", "venduto", "venduti", "verkocht", "verkauft", "vendu", "vendido")


def parse_amount(raw: str) -> float:
    """Convert a localized number ("1.234,50", "1,234.50", "45,5") to float."""
    s = raw.replace(" ", "").replace(" ", "")
    if "," in s and "." in s:
        # The right-most separator is the decimal one.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = f"{head.replace(',', '')}.{tail}" if len(tail) <= 2 else s.replace(",", "")
    elif "." in s:
        head, _, tail = s.rpartition(".")
        s = f"{head.replace('.', '')}.{tail}" if len(tail) <= 2 else s.replace(".", "")
    return float(s)


def parse_price(text: str) -> float | None:
    """Return the first currency amount found in ``text`` (price per ticket)."""
    m = _PRICE_RE.search(text.replace(" ", " "))
    if not m:
        return None
    return parse_amount(m.group(1) or m.group(2))


def parse_quantity(text: str) -> int | None:
    m = _QTY_RE.search(text)
    return int(m.group(1)) if m else None


def looks_sold(text: str) -> bool:
    low = text.lower()
    return any(re.search(rf"\b{w}\b", low) for w in _SOLD_WORDS)


@dataclass(frozen=True)
class Listing:
    url: str
    text: str
    price: float | None
    quantity: int | None

    @classmethod
    def from_card(cls, url: str, text: str) -> "Listing":
        return cls(url=url, text=text, price=parse_price(text), quantity=parse_quantity(text))


def select_candidates(
    listings: list[Listing],
    *,
    max_price: float | None,
    quantity: int,
    seen: set[str],
) -> list[Listing]:
    """Filter listings the bot should try, cheapest first.

    Listings without a readable price are kept only if no price limit is set.
    Listings whose advertised quantity is lower than requested are dropped.
    """
    out: list[Listing] = []
    unique: dict[str, Listing] = {}
    for item in listings:
        unique.setdefault(item.url, item)
    for item in unique.values():
        if item.url in seen or looks_sold(item.text):
            continue
        if max_price is not None and (item.price is None or item.price > max_price):
            continue
        if item.quantity is not None and item.quantity < quantity:
            continue
        out.append(item)
    out.sort(key=lambda l: (l.price is None, l.price or 0.0))
    return out
