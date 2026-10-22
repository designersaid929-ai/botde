import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
TEMP_DOWNLOAD_DIR = BASE_DIR / "temp_downloads"
TEMP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Config:
    # Telegram Bot Token
    BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    # Instagram Authentication
    IG_SESSION_ID: str = os.getenv("INSTAGRAM_SESSION_ID", "").strip()
    IG_CSRF_TOKEN: str = os.getenv("INSTAGRAM_CSRF_TOKEN", "").strip()
    IG_DS_USER_ID: str = os.getenv("INSTAGRAM_DS_USER_ID", "").strip()
    IG_USERNAME: str = os.getenv("INSTAGRAM_USERNAME", "").strip()
    IG_PASSWORD: str = os.getenv("INSTAGRAM_PASSWORD", "").strip()
    IG_SESSION_FILE: str = os.getenv("INSTAGRAM_SESSION_FILE", "").strip()

    # Limits & Delays
    DEFAULT_POSTS_LIMIT: int = int(os.getenv("DEFAULT_POSTS_LIMIT", "3"))
    MAX_POSTS_LIMIT: int = int(os.getenv("MAX_POSTS_LIMIT", "10"))
    USER_COOLDOWN_SECONDS: int = int(os.getenv("USER_COOLDOWN_SECONDS", "4"))
    MAX_CONCURRENT_DOWNLOADS: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Admin Notifications
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0")) if os.getenv("ADMIN_ID", "0").isdigit() else 0

    # Gemini AI Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

    # Channel Subscription Verification
    # Can be a single channel (@mychannel) or comma-separated (@ch1, @ch2, -100...)
    REQUIRED_CHANNELS: str = os.getenv("REQUIRED_CHANNELS", os.getenv("REQUIRED_CHANNEL", "")).strip()

    # Paths
    BASE_DIR: Path = BASE_DIR
    TEMP_DIR: Path = TEMP_DOWNLOAD_DIR

    def validate(self) -> None:
        """Validate critical configuration settings."""
        if not self.BOT_TOKEN or self.BOT_TOKEN == "your_telegram_bot_token_here":
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is not configured! "
                "Please set TELEGRAM_BOT_TOKEN in your .env file or environment variables."
            )


config = Config()
