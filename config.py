"""Application configuration loaded from environment variables.

A single Config class is enough for now; cPanel/Passenger and local dev share
the same code path. SQLite is the only DB backend for v1.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOADS_DIR = BASE_DIR / "static" / "uploads"
ORIGINALS_DIR = INSTANCE_DIR / "originals"


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")

    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    _DEFAULT_DB = INSTANCE_DIR / "ahantapulse.sqlite3"
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{_DEFAULT_DB}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOADS_DIR = UPLOADS_DIR
    UPLOAD_FOLDER = str(UPLOADS_DIR)
    ORIGINALS_DIR = ORIGINALS_DIR
    ORIGINALS_FOLDER = str(ORIGINALS_DIR)
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "256")) * 1024 * 1024

    ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif"}
    ALLOWED_AUDIO_EXT = {"mp3", "m4a", "wav", "ogg", "aac"}
    ALLOWED_VIDEO_EXT = {"mp4", "webm", "mov", "m4v"}
    ALLOWED_PORTRAIT_EXT = {"jpg", "jpeg", "png", "webp"}

    WATERMARK_TEXT = os.environ.get("WATERMARK_TEXT", "AHANTAPULSE.ONLINE")
    PORTRAIT_PREVIEW_MAX_WIDTH = int(os.environ.get("PORTRAIT_PREVIEW_MAX_WIDTH", "1600"))
    PORTRAIT_DOWNLOAD_TTL_HOURS = int(os.environ.get("PORTRAIT_DOWNLOAD_TTL_HOURS", "48"))
    PORTRAIT_MAX_DOWNLOADS = int(os.environ.get("PORTRAIT_MAX_DOWNLOADS", "5"))

    SITE_NAME = os.environ.get("SITE_NAME", "AhantaPulse")
    SITE_SLOGAN = os.environ.get("SITE_SLOGAN", "Your heartbeat, our community.")
    SITE_TAGLINE = os.environ.get(
        "SITE_TAGLINE",
        "News, stories and videos from the Ahanta — plus a community marketplace.",
    )
    SITE_REGION = os.environ.get("SITE_REGION", "Ahanta, Ghana")
    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")

    ALLOW_REGISTRATION = _as_bool(os.environ.get("ALLOW_REGISTRATION"), True)

    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@ahantapulse.online")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Atomic2@2020^")
    ADMIN_FORCE_RESET = _as_bool(os.environ.get("ADMIN_FORCE_RESET"), False)

    PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY", "")
    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_CURRENCY = os.environ.get("PAYSTACK_CURRENCY", "GHS")

    WTF_CSRF_TIME_LIMIT = None
