"""
settings.py — Configuration for HubSpot → Slack Daily CRM Digest

Loads environment variables, validates required config, and exposes a small
Settings class used by the digest script.
"""

import os
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


class Settings:
    """
    App settings loaded from environment variables.

    Priority:
    1. Environment variables
    2. .env file
    """

    # =========================================================================
    # Scalekit (required)
    # =========================================================================
    SCALEKIT_ENV_URL: str = os.getenv("SCALEKIT_ENV_URL", "")
    SCALEKIT_CLIENT_ID: str = os.getenv("SCALEKIT_CLIENT_ID", "")
    SCALEKIT_CLIENT_SECRET: str = os.getenv("SCALEKIT_CLIENT_SECRET", "")

    # =========================================================================
    # Service identifiers (required)
    # Use different identifiers if Slack and HubSpot are authorized under
    # different Scalekit accounts.
    # =========================================================================
    HUBSPOT_IDENTIFIER: Optional[str] = os.getenv("HUBSPOT_IDENTIFIER")
    SLACK_IDENTIFIER: Optional[str] = os.getenv("SLACK_IDENTIFIER")

    # =========================================================================
    # Digest configuration
    # =========================================================================
    # Slack channel ID for posting the morning summary (e.g., C01234567).
    # Leave empty to skip channel summary (DMs will still be sent if mapped).
    DIGEST_CHANNEL_ID: str = os.getenv("DIGEST_CHANNEL_ID", "")
    # Lookback window in hours for the daily digest (default: 24h).
    DIGEST_LOOKBACK_HOURS: int = int(os.getenv("DIGEST_LOOKBACK_HOURS", "24"))

    # =========================================================================
    # Mapping & Snapshot files
    # =========================================================================
    # Minimal mapping file:
    # {
    #   "84157204": { "slack_user_id": "U09JQLLKKMH" },
    #   "12345678": { "slack_user_id": "U01ABCDE2F3" }
    # }
    MAPPING_FILE: str = os.getenv("MAPPING_FILE", "mapping.json")

    # Snapshot file to store last-seen deal last_modified timestamps.
    SNAPSHOT_FILE: str = os.getenv("SNAPSHOT_FILE", "deal_snapshot.json")

    # =========================================================================
    # Optional allow/deny channel lists (not usually needed for the digest,
    # but kept as a safe guard if you expand features later).
    # =========================================================================
    _allowed_channels_str: str = os.getenv("ALLOWED_CHANNELS", "")
    ALLOWED_CHANNELS: List[str] = [c.strip() for c in _allowed_channels_str.split(",") if c.strip()]

    _denied_channels_str: str = os.getenv("DENIED_CHANNELS", "")
    DENIED_CHANNELS: List[str] = [c.strip() for c in _denied_channels_str.split(",") if c.strip()]

    # =========================================================================
    # Retry/backoff for connector actions
    # (these are read by your connector wrapper, if applicable)
    # =========================================================================
    RETRY_ATTEMPTS: int = int(os.getenv("RETRY_ATTEMPTS", "3"))
    RETRY_BACKOFF_SECONDS: int = int(os.getenv("RETRY_BACKOFF", "1"))

    # =========================================================================
    # Validation & helpers
    # =========================================================================
    @classmethod
    def validate(cls) -> None:
        """
        Validate required settings.
        """
        required = {
            "SCALEKIT_ENV_URL": cls.SCALEKIT_ENV_URL,
            "SCALEKIT_CLIENT_ID": cls.SCALEKIT_CLIENT_ID,
            "SCALEKIT_CLIENT_SECRET": cls.SCALEKIT_CLIENT_SECRET,
            "HUBSPOT_IDENTIFIER": cls.HUBSPOT_IDENTIFIER,
            "SLACK_IDENTIFIER": cls.SLACK_IDENTIFIER,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(
                "Missing required configuration: "
                + ", ".join(missing)
                + ". Check your .env."
            )

    @classmethod
    def is_channel_allowed(cls, channel_id: str) -> bool:
        """
        Allow/deny channel filter (mostly unused for the digest).
        """
        if channel_id in cls.DENIED_CHANNELS:
            return False
        if not cls.ALLOWED_CHANNELS:
            return True
        return channel_id in cls.ALLOWED_CHANNELS

    @classmethod
    def get_summary(cls) -> dict:
        """
        Safe summary for logging.
        """
        return {
            "scalekit_configured": bool(cls.SCALEKIT_ENV_URL and cls.SCALEKIT_CLIENT_ID),
            "hubspot_identifier_set": bool(cls.HUBSPOT_IDENTIFIER),
            "slack_identifier_set": bool(cls.SLACK_IDENTIFIER),
            "digest_channel_id": cls.DIGEST_CHANNEL_ID or "not set",
            "digest_lookback_hours": cls.DIGEST_LOOKBACK_HOURS,
            "mapping_file": cls.MAPPING_FILE,
            "snapshot_file": cls.SNAPSHOT_FILE,
            "retry_attempts": cls.RETRY_ATTEMPTS,
            "retry_backoff_seconds": cls.RETRY_BACKOFF_SECONDS,
        }


# Validate on import (fail fast)
try:
    Settings.validate()
    print("✅ Configuration loaded successfully")
    print(f"📋 Config summary: {Settings.get_summary()}")
except ValueError as e:
    print(f"❌ Configuration error: {e}")
    print("⚠️  Please create/update your .env with the required variables.")
