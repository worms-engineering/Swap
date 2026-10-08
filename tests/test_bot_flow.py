"""End-to-end test against a local fake of TicketSwap's pages."""

import functools
import http.server
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from ticketswap_bot import bot  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


class Handler(http.server.SimpleHTTPRequestHandler):
    routes = {
        "/event/concerto": "event.html",
        "/listing/concerto/1/aaa": "listing.html",
        "/listing/concerto/2/bbb": "listing.html",
        "/listing/concerto/3/ccc": "listing_sold.html",
        "/listing/concerto/4/ddd": "listing.html",
        "/event/festival": "event2.html",
        "/event/blocked": "blocked.html",
        "/listing/festival/7/ggg": "listing.html",
        "/listing/festival/8/hhh": "listing.html",
    }

    def do_GET(self):
        name = self.routes.get(self.path.split("?")[0])
        if not name:
            self.send_error(404)
            return
        body = (FIXTURES / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def make_settings(tmp_path, targets, **kw):
    kw.setdefault("max_runtime", 60)
    return bot.Settings(targets=targets, profile_dir=tmp_path / "profile", headless=True,
                        reserve_timeout=5, **kw)


def test_reserves_cheapest_available_listing(server, tmp_path, monkeypatch):
    notified = []
    monkeypatch.setattr(bot, "notify", lambda title, msg: notified.append(title))
    target = bot.EventTarget(url=f"{server}/event/concerto", max_price=100)
    result = bot.run(make_settings(tmp_path, [target]), keep_open=False)
    # Listing 3 (€40) is cheapest but already sold, so the bot moves on to listing 2.
    assert [r.url for r in result] == [f"{server}/listing/concerto/2/bbb"]
    assert target.seen == {f"{server}/listing/concerto/3/ccc"}
    assert notified == ["Biglietti riservati su TicketSwap! (concerto)"]


def test_watches_multiple_events_with_own_trigger_price(server, tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "notify", lambda *a: None)
    concerto = bot.EventTarget(url=f"{server}/event/concerto", max_price=100, quantity=2)
    festival = bot.EventTarget(url=f"{server}/event/festival", max_price=60)
    result = bot.run(make_settings(tmp_path, [concerto, festival]), keep_open=False)
    assert concerto.reserved.url.endswith("/listing/concerto/2/bbb")
    assert festival.reserved.url.endswith("/listing/festival/8/hhh")  # €70 is above its trigger price
    assert len(result) == 2


def test_stop_after_first(server, tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "notify", lambda *a: None)
    targets = [bot.EventTarget(url=f"{server}/event/concerto", max_price=100),
               bot.EventTarget(url=f"{server}/event/festival", max_price=60)]
    result = bot.run(make_settings(tmp_path, targets, stop_after_first=True), keep_open=False)
    assert len(result) == 1 and targets[1].reserved is None


def test_stops_when_nothing_matches(server, tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "notify", lambda *a: None)
    monkeypatch.setattr(bot, "MIN_INTERVAL", 0.1)
    target = bot.EventTarget(url=f"{server}/event/concerto", max_price=5)
    settings = make_settings(tmp_path, [target], interval=0.1, max_runtime=1)
    assert bot.run(settings, keep_open=False) == []


def test_stops_on_bot_protection_page(server, tmp_path, monkeypatch):
    notified = []
    monkeypatch.setattr(bot, "notify", lambda title, msg: notified.append(title))
    target = bot.EventTarget(url=f"{server}/event/blocked", max_price=100)
    assert bot.run(make_settings(tmp_path, [target]), keep_open=False) == []
    assert notified == ["TicketSwap ha bloccato il bot"]
