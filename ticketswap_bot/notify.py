"""User notifications: terminal, desktop (notify-send) and optional Telegram."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)


def notify(title: str, message: str) -> None:
    print(f"\a\n{'=' * 60}\n{title}\n{message}\n{'=' * 60}\n", flush=True)
    _desktop(title, message)
    _telegram(f"{title}\n{message}")


def _desktop(title: str, message: str) -> None:
    for cmd in (["notify-send", "-u", "critical", title, message],
                ["osascript", "-e", f"display notification {json.dumps(message)} with title {json.dumps(title)}"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, check=False, timeout=5)
            except Exception as exc:  # notification failure must never stop the bot
                log.debug("desktop notification failed: %s", exc)
            return


def _telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10)
    except Exception as exc:
        log.warning("Notifica Telegram fallita: %s", exc)
