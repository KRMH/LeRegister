"""Wiring: configuration to bot. Long polling only, no inbound port (AR14)."""

from __future__ import annotations

import logging
import sys

from telegram.error import InvalidToken

from leregister.adapters.clock import SystemClock
from leregister.adapters.llm import GroqInterpreter
from leregister.adapters.store import SqliteStore, StoreError
from leregister.adapters.telegram.bot import build_application
from leregister.config import ConfigError, Settings


log = logging.getLogger(__name__)


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
    store = SqliteStore(settings.db_path)
    try:
        store.open()
    except StoreError as exc:
        print(f"LeRegister cannot start: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    interpreter = (
        GroqInterpreter(settings.llm_api_key, settings.llm_model, settings.llm_timeout)
        if settings.llm_api_key
        else None
    )
    if interpreter is not None:
        log.info("free text is on (provider %s, model %s)", settings.llm_provider, settings.llm_model)
    else:
        log.info("free text is off: no LEREGISTER_LLM_API_KEY set")
    try:
        build_application(settings, SystemClock(), store, store, interpreter).run_polling()
    except InvalidToken:
        print("LeRegister cannot start: the bot token was rejected by Telegram", file=sys.stderr)
        raise SystemExit(2) from None
    finally:
        store.close()


if __name__ == "__main__":
    main()
