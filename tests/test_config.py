import pytest

from ticketswap_bot.__main__ import main
from ticketswap_bot.config import ConfigError, load_config

URL1 = "https://www.ticketswap.com/event/concerto/abc"
URL2 = "https://www.ticketswap.com/event/festival/def"


def write(tmp_path, text):
    p = tmp_path / "events.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_config_per_event_and_defaults(tmp_path):
    path = write(tmp_path, f"""
interval = 30
max_price = 50
quantity = 2
stop_after_first = true

[[event]]
url = "{URL1}"
max_price = 80

[[event]]
url = "{URL2}"
trigger_price = 40
quantity = 1

[[event]]
url = "{URL2}/x"
""")
    targets, opts = load_config(path)
    assert [(t.max_price, t.quantity) for t in targets] == [(80, 2), (40, 1), (50, 2)]
    assert opts == {"interval": 30, "stop_after_first": True}


@pytest.mark.parametrize("body,msg", [
    ("interval = 10", "almeno una"),
    ('[[event]]\nmax_price = 3', "manca url"),
    ('[[event]]\nurl = "https://example.com/x"', "TicketSwap"),
    (f'[[event]]\nurl = "{URL1}"\nprice = 3', "sconosciute"),
    (f'[[event]]\nurl = "{URL1}"\nquantity = 0', "almeno 1"),
    ("not toml [", "impossibile"),
])
def test_load_config_errors(tmp_path, body, msg):
    with pytest.raises(ConfigError, match=msg):
        load_config(write(tmp_path, body))


def test_cli_merges_urls_and_config(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr("ticketswap_bot.bot.run", lambda s: captured.setdefault("s", s) and [])
    path = write(tmp_path, f'interval = 30\n[[event]]\nurl = "{URL1}"\nmax_price = 80\n')
    main(["watch", "-c", str(path), URL2, "--trigger-price", "60"])
    s = captured["s"]
    # --trigger-price applies to command-line URLs; config events keep their own price.
    assert [(t.url, t.max_price) for t in s.targets] == [(URL1, 80), (URL2, 60)]
    assert s.interval == 30


def test_cli_requires_a_target():
    with pytest.raises(SystemExit):
        main(["watch"])
