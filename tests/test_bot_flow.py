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


def test_reserves_cheapest_available_listing(server, tmp_path, monkeypatch):
    notified = []
    monkeypatch.setattr(bot, "notify", lambda title, msg: notified.append(title))
    settings = bot.Settings(
        event_url=f"{server}/event/concerto",
        max_price=100,
        quantity=1,
        profile_dir=tmp_path / "profile",
        headless=True,
        max_runtime=60,
        reserve_timeout=5,
    )
    result = bot.run(settings, keep_open=False)
    # Listing 3 (€40) is cheapest but already sold, so the bot moves on to listing 2.
    assert result is not None
    assert result.url.endswith("/listing/concerto/2/bbb")
    assert settings.seen == {f"{server}/listing/concerto/3/ccc"}
    assert notified == ["Biglietti riservati su TicketSwap!"]


def test_stops_when_nothing_matches(server, tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "notify", lambda *a: None)
    monkeypatch.setattr(bot, "MIN_INTERVAL", 0.1)
    settings = bot.Settings(
        event_url=f"{server}/event/concerto",
        max_price=5,
        interval=0.1,
        profile_dir=tmp_path / "profile",
        headless=True,
        max_runtime=1,
    )
    assert bot.run(settings, keep_open=False) is None
