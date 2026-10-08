import pytest

from ticketswap_bot.parsing import Listing, looks_sold, parse_amount, parse_price, parse_quantity, select_candidates


@pytest.mark.parametrize("raw,expected", [
    ("45,50", 45.5), ("45.50", 45.5), ("1.234,50", 1234.5), ("1,234.50", 1234.5),
    ("1.234", 1234.0), ("1,234", 1234.0), ("30", 30.0), ("45,5", 45.5),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("text,expected", [
    ("2 tickets\n€ 55,50", 55.5), ("€45.00 per ticket", 45.0), ("£1,234.00", 1234.0),
    ("30,00 €", 30.0), ("EUR 30", 30.0), ("nessun prezzo", None), ("€ 12,00", 12.0),
])
def test_parse_price(text, expected):
    assert parse_price(text) == expected


def test_parse_quantity_and_sold():
    assert parse_quantity("2 tickets · €50") == 2
    assert parse_quantity("1 biglietto") == 1
    assert parse_quantity("€50") is None
    assert looks_sold("2 tickets · Sold")
    assert not looks_sold("Soldout Festival 1 ticket")  # word boundary


def test_select_candidates_filters_and_sorts():
    cards = [
        Listing.from_card("u1", "1 ticket €120,00"),
        Listing.from_card("u2", "2 tickets €55,50"),
        Listing.from_card("u3", "1 ticket €40,00"),
        Listing.from_card("u4", "2 tickets Sold €10,00"),
        Listing.from_card("u5", "no price"),
        Listing.from_card("u3", "duplicate"),
    ]
    got = select_candidates(cards, max_price=100, quantity=1, seen=set())
    assert [l.url for l in got] == ["u3", "u2"]
    got = select_candidates(cards, max_price=100, quantity=2, seen=set())
    assert [l.url for l in got] == ["u2"]
    got = select_candidates(cards, max_price=None, quantity=1, seen={"u3"})
    assert [l.url for l in got] == ["u2", "u1", "u5"]
