"""
Configuration management for Email Deadline Agent using python-dotenv.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Automatically load .env file from project root
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)


class AgentConfig:
    """Central configuration for email agent and LLM backends."""

    def __init__(self):
        # Email settings
        self.email_address: str = os.getenv("EMAIL_ADDRESS", "").strip()
        self.email_password: str = os.getenv("EMAIL_PASSWORD", "").strip()
        self.imap_host: str = os.getenv("IMAP_HOST", "imap.gmail.com").strip()
        self.imap_port: int = int(os.getenv("IMAP_PORT", "993"))
        self.use_ssl: bool = os.getenv("USE_SSL", "True").lower() in ("true", "1", "yes")

        # LLM Provider settings (Gemini is the designated AI model)
        self.llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

        # Operational settings
        self.fetch_limit: int = int(os.getenv("FETCH_LIMIT", "50"))
        # Read all emails (both read and unread) by default
        self.unread_only: bool = os.getenv("UNREAD_ONLY", "False").lower() in ("true", "1", "yes")
        # Filter emails to today only by default
        self.today_only: bool = os.getenv("TODAY_ONLY", "True").lower() in ("true", "1", "yes")
        self.mark_as_read: bool = os.getenv("MARK_AS_READ", "False").lower() in ("true", "1", "yes")
        self.output_path: str = os.getenv("OUTPUT_PATH", "deadlines.md").strip()
        self.timezone_str: str = os.getenv("TIMEZONE", "UTC").strip()
        # Approaching deadline alert window in minutes (1 hour)
        self.alert_window_minutes: int = int(os.getenv("ALERT_WINDOW_MINUTES", "60"))

        # If key is empty or dummy template string, fall back to heuristic
        if not self.gemini_api_key or self.gemini_api_key.startswith("AIzaSy...") or "xxxx" in self.gemini_api_key:
            self.gemini_api_key = ""
            self.llm_provider = "heuristic"

    def validate_live_credentials(self) -> None:
        """Validates that credentials required for live IMAP connection exist."""
        missing = []
        if not self.email_address or self.email_address == "your_email@gmail.com":
            missing.append("EMAIL_ADDRESS")
        if not self.email_password or "xxxx" in self.email_password:
            missing.append("EMAIL_PASSWORD")

        if missing:
            raise ValueError(
                f"Missing required live email credentials in .env: {', '.join(missing)}.\n"
                f"Please update your .env file or run with '--mock' to test with sample emails."
            )

    def summary_dict(self) -> dict:
        """Returns non-sensitive configuration parameters."""
        return {
            "email_address": self.email_address if self.email_address else "(Not configured)",
            "imap_host": self.imap_host,
            "imap_port": self.imap_port,
            "use_ssl": self.use_ssl,
            "llm_provider": self.llm_provider,
            "fetch_limit": self.fetch_limit,
            "unread_only": self.unread_only,
            "mark_as_read": self.mark_as_read,
            "output_path": self.output_path,
        }
