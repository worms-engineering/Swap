"""Run the bookmarklet in a real browser against a local fake of a TicketSwap event page."""

import http.server
import json
import os
import threading
import urllib.parse
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

from ticketswap_bot import bot  # noqa: E402
from ticketswap_bot.bookmarklet import bookmarklet_js, bookmarklet_url, build_page  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

LISTING = '<a href="/listing/x/{id}/h"><div>{qty} ticket</div><div>€ {price}</div></a>'


class State:
    listings: list[str] = []
    blocked = False
    deny_frames = False


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path != "/event/x":
            self.send_error(404)
            return
        if State.blocked:
            body = "<html><head><title>Verifying</title></head><body><p>Unable to verify.</p></body></html>"
        else:
            body = "<html><head><title>Evento - TicketSwap</title></head><body><h1>Evento</h1>" + "".join(State.listings) + "</body></html>"
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if State.deny_frames:
            self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def page():
    State.listings, State.blocked, State.deny_frames = [], False, False
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    # The bookmarklet only runs on ticketswap.* hosts: map one to the local server.
    port = httpd.server_address[1]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=os.environ.get("TICKETSWAP_BOT_BROWSER") or None,
            args=[f"--host-resolver-rules=MAP www.ticketswap.test 127.0.0.1:{port}"],
        )
        pg = browser.new_page()
        pg.on("dialog", lambda d: d.dismiss())
        yield pg
        browser.close()
    httpd.shutdown()


def run_bookmarklet(page, max_price, **kw):
    js = bookmarklet_js(max_price=max_price, **kw)
    # Tests poll fast; the real minimum interval is 10 s.
    js = js.replace('"quantity":', '"_minInterval": 0.3, "quantity":', 1)
    page.evaluate(js)


def wait_state(page, expr, timeout=15000):
    page.wait_for_function(f"() => window.__tsAlert && ({expr})", timeout=timeout)


def test_alarm_when_listing_hits_price(page):
    State.listings = [LISTING.format(id=1, qty=1, price="150,00"), LISTING.format(id=2, qty=1, price="90,00")]
    page.goto("http://www.ticketswap.test/event/x")
    run_bookmarklet(page, 100, interval=0.3)
    wait_state(page, "__tsAlert.checks >= 1")
    assert page.evaluate("__tsAlert.mode") == "frame"
    assert page.evaluate("[...__tsAlert.alerted]") == ["http://www.ticketswap.test/listing/x/2/h"]
    assert page.evaluate("__tsAlert.alarming")

    page.click('#ts-alert-panel [data-a="silence"]')
    State.listings.append(LISTING.format(id=3, qty=1, price="80,00"))
    State.listings.append('<a href="/listing/x/4/h"><div>1 ticket · Venduto</div><div>€ 10,00</div></a>')
    wait_state(page, "__tsAlert.alerted.size === 2")
    assert page.evaluate("__tsAlert.alarming")
    assert page.evaluate("__tsAlert.matches.map(m => m.price)") == [80, 90]
    assert "apri e compra" in page.inner_text("#ts-alert-panel")


def test_quantity_filter(page):
    State.listings = [LISTING.format(id=1, qty=1, price="50,00")]
    page.goto("http://www.ticketswap.test/event/x")
    run_bookmarklet(page, 100, interval=0.3, quantity=2)
    wait_state(page, "__tsAlert.checks >= 2")
    assert page.evaluate("__tsAlert.alerted.size") == 0
    assert not page.evaluate("__tsAlert.alarming")


def test_stops_on_verification_page(page):
    page.goto("http://www.ticketswap.test/event/x")
    State.blocked = True
    run_bookmarklet(page, 100, interval=0.3)
    wait_state(page, "!__tsAlert.running")
    assert "verifica" in page.inner_text("#ts-alert-panel")
    checks = page.evaluate("__tsAlert.checks")
    page.wait_for_timeout(1500)
    assert page.evaluate("__tsAlert.checks") == checks  # no further requests


def test_falls_back_to_fetch_when_framing_is_denied(page):
    State.deny_frames = True
    State.listings = [LISTING.format(id=5, qty=2, price="60,00")]
    page.goto("http://www.ticketswap.test/event/x")
    run_bookmarklet(page, 70, interval=0.3)
    wait_state(page, "__tsAlert.alerted.size === 1", timeout=40000)
    assert page.evaluate("__tsAlert.mode") == "fetch"


def test_refuses_other_sites(page):
    page.goto("about:blank")
    run_bookmarklet(page, 100)
    assert page.evaluate("window.__tsAlert === undefined")


def test_installer_page_builds_working_link(page, tmp_path):
    html_path = tmp_path / "bm.html"
    html_path.write_text(build_page(), encoding="utf-8")
    page.goto(html_path.as_uri())
    page.fill("#price", "75")
    href = page.get_attribute("#bm", "href")
    js = urllib.parse.unquote(href[len("javascript:"):])
    cfg = json.loads(js.split("const CFG = ", 1)[1].split(";", 1)[0])
    assert cfg == {"maxPrice": 75, "interval": 20, "quantity": 1}
    assert "≤ 75€" in page.inner_text("#bm")


def test_python_link_matches_page_defaults():
    url = bookmarklet_url(max_price=80, interval=20, quantity=2)
    assert url.startswith("javascript:")
    assert '"maxPrice": 80' in urllib.parse.unquote(url)


def test_committed_page_is_up_to_date():
    assert (ROOT / "bookmarklet.html").read_text(encoding="utf-8") == build_page(), (
        "rigenera con: python -m ticketswap_bot bookmarklet --no-open"
    )
