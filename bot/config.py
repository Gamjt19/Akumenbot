"""
Configuration loader.

Reads all runtime configuration from environment variables (via .env in
local dev, or real environment variables in Docker/production). Nothing
here is hardcoded — no user IDs, no tokens, no channel IDs.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _optional_int(name: str) -> int | None:
    value = os.getenv(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be an integer, got: {value!r}") from exc


@dataclass(frozen=True)
class Config:
    discord_token: str
    database_url: str
    timezone: str
    guild_id: int | None
    submission_channel_id: int | None
    admin_channel_id: int | None
    trainer_channel_id: int | None
    assignments_channel_id: int | None
    achievements_channel_id: int | None
    trainer_role_name: str
    daily_report_hour: int
    daily_report_minute: int

    @classmethod
    def load(cls) -> "Config":
        trainer_channel = _optional_int("TRAINER_CHANNEL_ID") or _optional_int("ADMIN_CHANNEL_ID")
        return cls(
            discord_token=_require("DISCORD_TOKEN"),
            database_url=os.getenv("DB_URL") or os.getenv("DATABASE_URL", "sqlite:///data/challenge.db"),
            timezone=os.getenv("TIMEZONE", "Asia/Kolkata"),
            guild_id=_optional_int("GUILD_ID"),
            submission_channel_id=_optional_int("SUBMISSION_CHANNEL_ID"),
            admin_channel_id=trainer_channel,
            trainer_channel_id=trainer_channel,
            assignments_channel_id=_optional_int("ASSIGNMENTS_CHANNEL_ID"),
            achievements_channel_id=_optional_int("ACHIEVEMENTS_CHANNEL_ID"),
            trainer_role_name=os.getenv("TRAINER_ROLE_NAME", "trainer"),
            daily_report_hour=int(os.getenv("DAILY_REPORT_HOUR", "0")),
            daily_report_minute=int(os.getenv("DAILY_REPORT_MINUTE", "5")),
        )


config = Config.load()
