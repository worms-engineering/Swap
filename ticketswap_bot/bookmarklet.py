"""Build the price-alert bookmarklet and the page used to install it.

The bookmarklet runs in the user's own browser tab on TicketSwap: it re-reads
the event page periodically and sounds an alarm when a listing hits the
trigger price. It never buys: the user opens the listing and pays by hand.
"""

from __future__ import annotations

import html
import json
import urllib.parse
from pathlib import Path

STATIC = Path(__file__).with_name("static")
PLACEHOLDER = "__CONFIG__"
INCLUDE = "/*@common*/"


def minified_source(name: str = "alert") -> str:
    """static/<name>.js with common.js inlined, without comment lines and indentation.

    Newlines are kept, so automatic semicolon insertion is unaffected.
    """
    source = (STATIC / f"{name}.js").read_text(encoding="utf-8")
    source = source.replace(INCLUDE, (STATIC / "common.js").read_text(encoding="utf-8"), 1)
    lines = []
    for line in source.splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            lines.append(line)
    return "\n".join(lines)


def config(max_price: float | None = None, interval: float = 20, quantity: int = 1) -> dict:
    return {"maxPrice": max_price, "interval": interval, "quantity": quantity}


def bookmarklet_js(**cfg) -> str:
    return minified_source().replace(PLACEHOLDER, json.dumps(config(**cfg)), 1)


def bookmarklet_url(**cfg) -> str:
    return "javascript:" + urllib.parse.quote(bookmarklet_js(**cfg), safe="")


def prices_js() -> str:
    return minified_source("prices")


def prices_url() -> str:
    return "javascript:" + urllib.parse.quote(prices_js(), safe="")


def build_page(max_price: float | None = None, interval: float = 20, quantity: int = 1) -> str:
    template = (STATIC / "bookmarklet_page.html").read_text(encoding="utf-8")
    src = json.dumps(minified_source()).replace("</", "<\\/")
    values = {
        "{{SOURCE}}": src,
        "{{PRICES_HREF}}": html.escape(prices_url()),
        "{{HREF}}": html.escape(bookmarklet_url(max_price=max_price, interval=interval, quantity=quantity)),
        "{{PRICE}}": "" if max_price is None else f"{max_price:g}",
        "{{INTERVAL}}": f"{interval:g}",
        "{{QUANTITY}}": str(quantity),
    }
    for key, value in values.items():
        template = template.replace(key, value)
    return template
