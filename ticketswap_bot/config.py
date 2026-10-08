"""Load watch targets from a TOML file.

Example::

    interval = 20

    [[event]]
    url = "https://www.ticketswap.com/event/..."
    max_price = 80
    quantity = 2

    [[event]]
    url = "https://www.ticketswap.com/event/..."
    max_price = 45
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .bot import EventTarget

GLOBAL_KEYS = {"interval", "max_runtime", "stop_after_first", "max_price", "quantity"}
EVENT_KEYS = {"url", "max_price", "trigger_price", "quantity"}


class ConfigError(ValueError):
    pass


def make_target(url: str, max_price: float | None, quantity: int) -> EventTarget:
    if "ticketswap." not in url:
        raise ConfigError(f"non è un URL di TicketSwap: {url}")
    if quantity < 1:
        raise ConfigError(f"quantity deve essere almeno 1 ({url})")
    if max_price is not None and max_price <= 0:
        raise ConfigError(f"max_price deve essere positivo ({url})")
    return EventTarget(url=url, max_price=max_price, quantity=quantity)


def load_config(path: Path) -> tuple[list[EventTarget], dict[str, Any]]:
    """Return (targets, global options). Per-event values override global defaults."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"impossibile leggere {path}: {exc}") from exc

    unknown = set(data) - GLOBAL_KEYS - {"event"}
    if unknown:
        raise ConfigError(f"opzioni sconosciute: {', '.join(sorted(unknown))}")
    events = data.get("event", [])
    if not isinstance(events, list) or not events:
        raise ConfigError("serve almeno una sezione [[event]] con url")

    targets = []
    for i, ev in enumerate(events, 1):
        unknown = set(ev) - EVENT_KEYS
        if unknown:
            raise ConfigError(f"evento {i}: opzioni sconosciute: {', '.join(sorted(unknown))}")
        if "url" not in ev:
            raise ConfigError(f"evento {i}: manca url")
        price = ev.get("max_price", ev.get("trigger_price", data.get("max_price")))
        targets.append(make_target(ev["url"], price, int(ev.get("quantity", data.get("quantity", 1)))))
    options = {k: data[k] for k in ("interval", "max_runtime", "stop_after_first") if k in data}
    return targets, options
