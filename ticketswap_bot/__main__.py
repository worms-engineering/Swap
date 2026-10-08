"""CLI: ``python -m ticketswap_bot login`` / ``python -m ticketswap_bot watch URL``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import bot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ticketswap_bot",
        description="Riserva biglietti su TicketSwap; il pagamento resta manuale.",
    )
    parser.add_argument("--profile", type=Path, default=bot.Settings.__dataclass_fields__["profile_dir"].default,
                        help="cartella del profilo browser (contiene la sessione di login)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="apre il browser per effettuare il login una volta")

    watch = sub.add_parser("watch", help="monitora un evento e riserva il primo biglietto compatibile")
    watch.add_argument("event_url", help="URL della pagina evento / tipo di biglietto su TicketSwap")
    watch.add_argument("--max-price", type=float, help="prezzo massimo per biglietto")
    watch.add_argument("--quantity", type=int, default=1, help="numero di biglietti (default 1)")
    watch.add_argument("--interval", type=float, default=20.0,
                       help=f"secondi tra un controllo e l'altro (minimo {bot.MIN_INTERVAL:.0f}, default 20)")
    watch.add_argument("--max-runtime", type=float, help="ferma il bot dopo N minuti")
    watch.add_argument("--headless", action="store_true", help="browser invisibile (sconsigliato)")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command == "login":
        bot.login(args.profile)
        return 0

    if "ticketswap." not in args.event_url:
        parser.error("l'URL deve essere una pagina di TicketSwap")
    if args.quantity < 1:
        parser.error("--quantity deve essere almeno 1")

    settings = bot.Settings(
        event_url=args.event_url,
        max_price=args.max_price,
        quantity=args.quantity,
        interval=args.interval,
        profile_dir=args.profile,
        headless=args.headless,
        max_runtime=args.max_runtime * 60 if args.max_runtime else None,
    )
    try:
        result = bot.run(settings)
    except KeyboardInterrupt:
        print("\nInterrotto.")
        return 130
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
