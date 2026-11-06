"""Settings from the environment, with a `.env` file as fallback (AR16)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ENV_FILE = Path.home() / ".leregister" / ".env"
ENV_FILE_VAR = "LEREGISTER_ENV_FILE"


class ConfigError(Exception):
    """A required setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    owner_id: int
    chalet_count: int = 40
    max_stay: int = 60

    @classmethod
    def load(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Load settings. Real environment variables win over the `.env` file."""
        source = os.environ if env is None else env
        merged = {**_read_env_file(_env_file_path(source)), **{k: v for k, v in source.items() if v.strip()}}
        return cls(
            bot_token=_required(merged, "LEREGISTER_BOT_TOKEN"),
            owner_id=_integer(merged, "LEREGISTER_OWNER_ID", required=True),
            chalet_count=_integer(merged, "LEREGISTER_CHALET_COUNT", default=40),
            max_stay=_integer(merged, "LEREGISTER_MAX_STAY", default=60),
        )


def _env_file_path(source: Mapping[str, str]) -> Path:
    custom = source.get(ENV_FILE_VAR)
    return Path(custom) if custom else DEFAULT_ENV_FILE


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"Cannot read settings file {path}: {exc}") from None
    for raw in text.splitlines():
        line = raw.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _required(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise ConfigError(f"Missing required setting {key}")
    return value


def _integer(
    env: Mapping[str, str],
    key: str,
    *,
    required: bool = False,
    default: int | None = None,
) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        if required:
            raise ConfigError(f"Missing required setting {key}")
        if default is None:
            raise ConfigError(f"Missing required setting {key}")
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"Setting {key} must be a whole number") from None
    if value <= 0:
        raise ConfigError(f"Setting {key} must be positive")
    return value
