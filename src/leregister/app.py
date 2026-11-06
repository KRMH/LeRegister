"""Wiring: configuration to bot. Long polling only, no inbound port (AR14)."""

from __future__ import annotations

import logging
import sys

from telegram.error import InvalidToken

from leregister.adapters.clock import SystemClock
from leregister.adapters.telegram.bot import build_application
from leregister.config import ConfigError, Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # httpx logs full request URLs, which contain the bot token
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        settings = Settings.load()
    except ConfigError as exc:
        print(f"LeRegister cannot start: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    try:
        build_application(settings, SystemClock()).run_polling()
    except InvalidToken:
        print("LeRegister cannot start: the bot token was rejected by Telegram", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
