from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_allowed_user_ids: set[int]
    todoist_api_token: str
    openai_api_key: str | None
    openai_model: str | None
    log_level: str
    poll_interval_seconds: float


class ConfigError(ValueError):
    pass


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _parse_allowed_user_ids(raw: str) -> set[int]:
    if not raw.strip():
        raise ConfigError("TELEGRAM_ALLOWED_USER_IDS must contain at least one user id")

    user_ids: set[int] = set()
    for chunk in raw.split(","):
        item = chunk.strip()
        if not item:
            continue
        try:
            user_ids.add(int(item))
        except ValueError as exc:
            raise ConfigError(f"Invalid TELEGRAM_ALLOWED_USER_IDS entry: {item}") from exc

    if not user_ids:
        raise ConfigError("TELEGRAM_ALLOWED_USER_IDS did not contain valid numeric ids")
    return user_ids


def load_settings() -> Settings:
    load_dotenv()

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip() or None
    openai_model = os.getenv("OPENAI_MODEL", "").strip() or None

    return Settings(
        telegram_bot_token=_require_env("TELEGRAM_BOT_TOKEN"),
        telegram_allowed_user_ids=_parse_allowed_user_ids(_require_env("TELEGRAM_ALLOWED_USER_IDS")),
        todoist_api_token=_require_env("TODOIST_API_TOKEN"),
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        log_level=os.getenv("LOG_LEVEL", "INFO").strip() or "INFO",
        poll_interval_seconds=float(os.getenv("POLL_INTERVAL_SECONDS", "2")),
    )
