"""Browser automation: watch an event page and reserve the first matching listing.

The bot never touches payment: once tickets are in the cart (TicketSwap holds
them for a limited time) it notifies the user and leaves the browser open so
the purchase can be completed by hand.
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, TimeoutError as PWTimeout, sync_playwright

from .notify import notify
from .parsing import Listing, select_candidates

log = logging.getLogger(__name__)

BASE_URL = "https://www.ticketswap.com"
MIN_INTERVAL = 5.0

# Text matchers are multilingual because TicketSwap localizes its UI.
BUY_BUTTON_RE = re.compile(
    r"^\s*(buy|koop|acquista|compra|comprar|kaufen|acheter|kup|køb|köp|kjøp)\b",
    re.IGNORECASE,
)
RESERVED_RE = re.compile(
    r"reserved|riservat|gereserveerd|reserviert|réservé|reservad|in your cart|nel carrello|in je winkelmand",
    re.IGNORECASE,
)
CHECKOUT_URL_RE = re.compile(r"/(cart|checkout|basket|winkelmand|reserv)", re.IGNORECASE)
CHALLENGE_RE = re.compile(r"captcha|are you human|verify you are|access denied|too many requests", re.IGNORECASE)

LISTING_LINK_SELECTOR = 'a[href*="/listing/"]'


@dataclass
class Settings:
    event_url: str
    max_price: float | None = None
    quantity: int = 1
    interval: float = 20.0
    profile_dir: Path = Path.home() / ".ticketswap-bot" / "profile"
    headless: bool = False
    max_runtime: float | None = None  # seconds; None = forever
    reserve_timeout: float = 15.0
    seen: set[str] = field(default_factory=set)


class ChallengeDetected(RuntimeError):
    """TicketSwap showed a captcha / rate-limit page: the user must intervene."""


def open_context(pw, profile_dir: Path, headless: bool) -> BrowserContext:
    """Persistent profile so the TicketSwap login done by the user is reused."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    return pw.chromium.launch_persistent_context(
        str(profile_dir),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        locale="it-IT",
        # Optional: use an installed Chrome/Chromium instead of Playwright's bundled one.
        executable_path=os.environ.get("TICKETSWAP_BOT_BROWSER") or None,
    )


def login(profile_dir: Path) -> None:
    """Open TicketSwap so the user can log in manually; the session is saved in the profile."""
    with sync_playwright() as pw:
        ctx = open_context(pw, profile_dir, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(BASE_URL)
        print("Effettua il login su TicketSwap nella finestra del browser.")
        input("Quando hai finito premi INVIO qui per salvare la sessione... ")
        ctx.close()


def collect_listings(page: Page) -> list[Listing]:
    cards = page.eval_on_selector_all(
        LISTING_LINK_SELECTOR,
        "els => els.map(e => ({href: e.href, text: e.innerText || ''}))",
    )
    return [Listing.from_card(c["href"].split("?")[0], c["text"]) for c in cards]


def check_challenge(page: Page, status: int | None) -> None:
    if status == 429 or status == 403:
        raise ChallengeDetected(f"HTTP {status}")
    try:
        title = page.title()
    except Exception:
        title = ""
    if CHALLENGE_RE.search(title):
        raise ChallengeDetected(title)


def load_event(page: Page, url: str) -> list[Listing]:
    resp = page.goto(url, wait_until="domcontentloaded")
    check_challenge(page, resp.status if resp else None)
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except PWTimeout:
        pass
    return collect_listings(page)


def _select_quantity(page: Page, quantity: int) -> None:
    if quantity <= 1:
        return
    select = page.locator("select").first
    if select.count():
        try:
            select.select_option(str(quantity), timeout=2000)
            return
        except Exception:
            log.debug("quantity <select> not usable")
    # Fallback: "+" stepper buttons.
    plus = page.get_by_role("button", name=re.compile(r"^\+$|increase|aumenta|meer", re.IGNORECASE)).first
    for _ in range(quantity - 1):
        if not plus.count():
            break
        plus.click(timeout=2000)


def try_reserve(page: Page, listing: Listing, quantity: int, timeout: float) -> bool:
    """Open a listing and press the buy button. Returns True when tickets are reserved."""
    log.info("Provo a riservare: %s (prezzo %s)", listing.url, listing.price)
    resp = page.goto(listing.url, wait_until="domcontentloaded")
    check_challenge(page, resp.status if resp else None)

    button = page.get_by_role("button", name=BUY_BUTTON_RE).or_(
        page.get_by_role("link", name=BUY_BUTTON_RE)
    ).first
    try:
        button.wait_for(state="visible", timeout=5000)
    except PWTimeout:
        log.info("Nessun pulsante di acquisto: annuncio probabilmente già venduto.")
        return False
    if not button.is_enabled():
        log.info("Pulsante di acquisto disabilitato.")
        return False

    _select_quantity(page, quantity)
    button.click()

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if CHECKOUT_URL_RE.search(page.url):
            return True
        try:
            if page.get_by_text(RESERVED_RE).first.is_visible():
                return True
        except Exception:
            pass
        page.wait_for_timeout(300)
    log.info("Nessuna conferma di prenotazione entro %.0fs.", timeout)
    return False


def wait_for_user(ctx: BrowserContext) -> None:
    """Keep the browser open until the user closes it (or presses Ctrl+C)."""
    print("Il browser resta aperto: completa il pagamento manualmente, poi chiudi la finestra.")
    try:
        while any(not p.is_closed() for p in ctx.pages):
            ctx.pages[0].wait_for_timeout(1000)
    except KeyboardInterrupt:
        pass
    except Exception:
        pass  # browser closed by the user


def run(settings: Settings, *, keep_open: bool = True) -> Listing | None:
    """Poll the event page until a listing is reserved. Returns the reserved listing."""
    interval = max(settings.interval, MIN_INTERVAL)
    started = time.monotonic()
    backoff = interval
    with sync_playwright() as pw:
        ctx = open_context(pw, settings.profile_dir, settings.headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            while True:
                if settings.max_runtime is not None and time.monotonic() - started > settings.max_runtime:
                    log.info("Tempo massimo raggiunto, mi fermo.")
                    return None
                try:
                    listings = load_event(page, settings.event_url)
                    candidates = select_candidates(
                        listings,
                        max_price=settings.max_price,
                        quantity=settings.quantity,
                        seen=settings.seen,
                    )
                    log.info("%d annunci trovati, %d compatibili.", len(listings), len(candidates))
                    for listing in candidates:
                        if try_reserve(page, listing, settings.quantity, settings.reserve_timeout):
                            notify(
                                "Biglietti riservati su TicketSwap!",
                                f"{listing.url}\nPrezzo: {listing.price}\n"
                                "Completa il pagamento prima che la prenotazione scada.",
                            )
                            if keep_open and not settings.headless:
                                wait_for_user(ctx)
                            return listing
                        settings.seen.add(listing.url)
                    backoff = interval
                except ChallengeDetected as exc:
                    backoff = min(backoff * 2, 600)
                    notify(
                        "TicketSwap richiede una verifica",
                        f"{exc}. Risolvila nel browser se richiesto; riprovo tra {backoff:.0f}s.",
                    )
                except PWTimeout as exc:
                    log.warning("Timeout di caricamento: %s", exc)
                sleep_for = backoff * random.uniform(0.8, 1.2)
                log.debug("Attendo %.1fs", sleep_for)
                page.wait_for_timeout(sleep_for * 1000)
        finally:
            try:
                ctx.close()
            except Exception:
                pass
