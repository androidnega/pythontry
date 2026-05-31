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
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "256")) * 1024 * 1024

    ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif"}
    ALLOWED_AUDIO_EXT = {"mp3", "m4a", "wav", "ogg", "aac"}
    ALLOWED_VIDEO_EXT = {"mp4", "webm", "mov", "m4v"}

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

    WTF_CSRF_TIME_LIMIT = None
