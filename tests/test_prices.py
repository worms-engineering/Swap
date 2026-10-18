"""Run the original-price bookmarklet against a local fake of TicketSwap."""

import collections
import http.server
import os
import threading

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

from ticketswap_bot.bookmarklet import prices_js  # noqa: E402

CARD = '<a href="/listing/x/{id}/h"><div>{qty} biglietto • {price} € / biglietto</div><div>Sezione 301</div></a>'
LISTINGS = {
    # Original price shown as text on the listing page.
    "/listing/x/1/h": "<p>Prezzo originale</p><p>85,00 €</p>",
    # Only in embedded page data, as cents.
    "/listing/x/2/h": '<script id="__NEXT_DATA__" type="application/json">'
                      '{"props":{"listing":{"price":{"amount":11000},"originalPrice":{"amount":12000,"currency":"EUR"}}}}</script>',
    # No original price anywhere.
    "/listing/x/3/h": "<p>Nessun dettaglio</p>",
    "/listing/x/4/h": "<p>Original price: €50.00</p>",
}


DEFAULT_CARDS = [(1, 1, "99,19"), (2, 2, "110,00"), (3, 1, "140,00")]


class State:
    blocked = False
    event_blocked = False
    cards: list = []
    hits: collections.Counter = collections.Counter()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        State.hits[path] += 1
        if State.blocked and path.startswith("/listing/"):
            body = "<html><head><title>Verifying</title></head><body>Unable to verify.</body></html>"
        elif path == "/event/x" and State.event_blocked:
            body = "<html><head><title>Verifying</title></head><body>Unable to verify.</body></html>"
        elif path == "/event/x":
            cards = "".join(CARD.format(id=i, qty=q, price=p) for i, q, p in State.cards)
            body = f"<html lang='it'><head><title>Evento</title></head><body><h1>Evento</h1><div id='list'>{cards}</div></body></html>"
        elif path in LISTINGS:
            body = f"<html><head><title>Annuncio</title></head><body><h1>Annuncio</h1>{LISTINGS[path]}</body></html>"
        else:
            self.send_error(404)
            return
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def page():
    State.blocked = False
    State.event_blocked = False
    State.cards = list(DEFAULT_CARDS)
    State.hits = collections.Counter()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=os.environ.get("TICKETSWAP_BOT_BROWSER") or None,
            args=[f"--host-resolver-rules=MAP www.ticketswap.test 127.0.0.1:{port}"],
        )
        pg = browser.new_page()
        pg.on("dialog", lambda d: d.dismiss())
        pg.goto("http://www.ticketswap.test/event/x")
        yield pg
        browser.close()
    httpd.shutdown()


def run(page, refresh=0):
    page.evaluate("window.__tsPricesGapMs = 50")
    # Tests refresh fast; the real minimum is 20 s.
    js = prices_js(refresh).replace('{"refresh":', '{"_minRefresh": 0.2, "refresh":', 1)
    # The bookmarklet's promise never settles (its worker keeps running): don't await it.
    page.evaluate("src => { (0, eval)(src); }", js)


def badges(page):
    return page.eval_on_selector_all(".ts-orig", "els => els.map(e => e.textContent)")


def wait_done(page, n=3):
    page.wait_for_function(
        f"() => [...document.querySelectorAll('.ts-orig')].filter(b => !b.textContent.includes('…')).length >= {n}",
        timeout=15000,
    )


def test_shows_original_price_and_difference(page):
    run(page)
    wait_done(page)
    assert badges(page) == [
        "Originale 85,00 € · +17%",
        "Originale 120,00 € · -8%",
        "Prezzo originale: n.d.",
    ]
    panel = page.inner_text("#ts-prices-panel")
    assert "Letti 3/3 annunci" in panel
    # Best deal first: -8% before +17%.
    assert panel.index("110,00") < panel.index("99,19")


def test_results_are_cached_across_reloads(page):
    run(page)
    wait_done(page)
    assert sum(v for k, v in State.hits.items() if k.startswith("/listing/")) == 3
    page.reload()
    run(page)
    wait_done(page)
    page.wait_for_timeout(500)
    assert sum(v for k, v in State.hits.items() if k.startswith("/listing/")) == 3
    assert badges(page)[0] == "Originale 85,00 € · +17%"


def test_new_cards_get_a_badge(page):
    run(page)
    wait_done(page)
    page.evaluate("""document.getElementById('list').insertAdjacentHTML('beforeend',
        '<a href="/listing/x/4/h"><div>1 biglietto • 45,00 € / biglietto</div></a>')""")
    wait_done(page, 4)
    assert badges(page)[3] == "Originale 50,00 € · -10%"


def test_badges_survive_rerender(page):
    run(page)
    wait_done(page)
    # Simulate the site re-rendering the list: cards replaced by fresh nodes.
    page.evaluate("const l = document.getElementById('list'); l.innerHTML = l.innerHTML.replace(/<span class=\"ts-orig\"[^>]*>[^<]*<\\/span>/g, '')")
    wait_done(page)
    assert len(badges(page)) == 3


def test_stops_on_verification_page(page):
    State.blocked = True
    run(page)
    page.wait_for_function("() => window.__tsPrices && !window.__tsPrices.running", timeout=10000)
    assert "verifica" in page.inner_text("#ts-prices-panel")
    hits = sum(v for k, v in State.hits.items() if k.startswith("/listing/"))
    page.wait_for_timeout(500)
    assert hits == 1 == sum(v for k, v in State.hits.items() if k.startswith("/listing/"))


def test_close_removes_everything(page):
    run(page)
    wait_done(page)
    page.click('#ts-prices-panel [data-a="close"]')
    assert badges(page) == []
    assert page.evaluate("window.__tsPrices === undefined")


def event_hits():
    return State.hits["/event/x"]


def test_refresh_shows_new_and_drops_removed_listings(page):
    run(page, refresh=0.5)
    wait_done(page)
    page.wait_for_function("() => window.__tsPrices.refreshes >= 1")
    assert "nuovo" not in page.inner_text("#ts-prices-panel")  # baseline: nothing is new yet
    State.cards = [(1, 1, "99,19"), (3, 1, "140,00"), (4, 1, "45,00")]  # 2 sold, 4 listed
    page.wait_for_function("() => document.getElementById('ts-prices-panel').innerText.includes('-10%')", timeout=15000)
    panel = page.inner_text("#ts-prices-panel")
    assert "🆕 1 nuovo annuncio" in panel
    assert "🆕 45,00 € (originale 50,00 €, -10%)" in panel
    assert "110,00" not in panel  # removed listing no longer offered as a deal
    assert "🔄 aggiornato alle" in panel


def test_refresh_reads_listings_not_rendered_on_screen(page):
    # The site renders only part of the list; the background read sees all of it.
    page.evaluate("document.querySelector('a[href=\"/listing/x/3/h\"]').remove()")
    run(page, refresh=30)
    wait_done(page, 2)
    page.wait_for_function("() => document.getElementById('ts-prices-panel').innerText.includes('Letti 3/3')", timeout=15000)
    assert "nuovo" not in page.inner_text("#ts-prices-panel")


def test_refresh_off(page):
    before = event_hits()
    run(page, refresh=0)
    wait_done(page)
    page.wait_for_timeout(1000)
    assert event_hits() == before
    assert "🔄" not in page.inner_text("#ts-prices-panel")


def test_refresh_stops_on_verification_page(page):
    run(page, refresh=0.3)
    wait_done(page)
    State.event_blocked = True
    page.wait_for_function("() => !window.__tsPrices.running", timeout=15000)
    assert "verifica" in page.inner_text("#ts-prices-panel")
    hits = event_hits()
    page.wait_for_timeout(1000)
    assert event_hits() == hits
