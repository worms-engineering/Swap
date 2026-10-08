"""CLI: ``python -m ticketswap_bot login`` / ``python -m ticketswap_bot watch URL [URL ...]``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import bot
from .config import ConfigError, load_config, make_target


def main(argv: list[str] | None = None) -> int:
    # Shared options, accepted both before and after the subcommand.
    # SUPPRESS keeps a subcommand from resetting a value given before it.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", type=Path, default=argparse.SUPPRESS,
                        help="cartella del profilo browser (contiene la sessione di login)")
    common.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS,
                        help="log dettagliati")
    parser = argparse.ArgumentParser(
        prog="ticketswap_bot",
        description="Riserva biglietti su TicketSwap; il pagamento resta manuale.",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", parents=[common], help="apre il browser per effettuare il login una volta")

    watch = sub.add_parser("watch", parents=[common],
                           help="monitora uno o più eventi e riserva i biglietti compatibili")
    watch.add_argument("event_urls", nargs="*", metavar="URL",
                       help="URL delle pagine evento / tipo di biglietto su TicketSwap")
    watch.add_argument("-c", "--config", type=Path,
                       help="file TOML con più eventi, ognuno con il proprio prezzo (vedi events.example.toml)")
    watch.add_argument("--max-price", "--trigger-price", dest="max_price", type=float,
                       help="prezzo massimo per biglietto: riserva solo annunci a questo prezzo o meno")
    watch.add_argument("--quantity", type=int, help="numero di biglietti (default 1)")
    watch.add_argument("--interval", type=float,
                       help=f"secondi tra un giro di controlli e l'altro (minimo {bot.MIN_INTERVAL:.0f}, default 20)")
    watch.add_argument("--max-runtime", type=float, help="ferma il bot dopo N minuti")
    watch.add_argument("--stop-after-first", action="store_true", default=None,
                       help="fermati dopo la prima prenotazione invece di continuare con gli altri eventi")
    watch.add_argument("--headless", action="store_true", help="browser invisibile (sconsigliato)")

    args = parser.parse_args(argv)
    args.verbose = getattr(args, "verbose", False)
    args.profile = getattr(args, "profile", bot.Settings.__dataclass_fields__["profile_dir"].default)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command == "login":
        bot.login(args.profile)
        return 0

    targets: list[bot.EventTarget] = []
    options: dict = {}
    try:
        if args.config:
            targets, options = load_config(args.config)
        targets += [make_target(url, args.max_price, args.quantity or 1) for url in args.event_urls]
    except ConfigError as exc:
        parser.error(str(exc))
    if not targets:
        parser.error("indica almeno un URL oppure --config")

    interval = args.interval if args.interval is not None else options.get("interval", 20.0)
    max_runtime = args.max_runtime if args.max_runtime is not None else options.get("max_runtime")
    stop_first = args.stop_after_first if args.stop_after_first is not None else options.get("stop_after_first", False)

    for t in targets:
        price = f"≤ {t.max_price:g}" if t.max_price is not None else "qualsiasi prezzo"
        print(f"• {t.label}: {t.quantity} biglietto/i, {price}")

    settings = bot.Settings(
        targets=targets,
        interval=float(interval),
        profile_dir=args.profile,
        headless=args.headless,
        max_runtime=float(max_runtime) * 60 if max_runtime else None,
        stop_after_first=bool(stop_first),
    )
    try:
        reserved = bot.run(settings)
    except KeyboardInterrupt:
        print("\nInterrotto.")
        return 130
    return 0 if reserved else 1


if __name__ == "__main__":
    sys.exit(main())
