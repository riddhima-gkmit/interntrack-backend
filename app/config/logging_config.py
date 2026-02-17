"""One-time logging setup (level, format, stdout). Called from main on startup."""

import logging
import sys

from app.config import settings


def setup_logging() -> None:
    """Configure structured logging for the application. Call once at startup (e.g. in main)."""
    # Map LOG_LEVEL env (e.g. "DEBUG", "INFO") to logging constant; invalid value falls back to INFO.
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",  # time | LEVEL | logger name | message
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],  # Stdout so logs work in containers and don't mix with stderr.
        force=True,  # Override any existing logging config (e.g. from libraries).
    )
