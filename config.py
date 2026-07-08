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

    # Public site is served over HTTPS (cPanel / reverse proxy). Force
    # Flask's url_for(..., _external=True) to emit https:// so Open Graph
    # preview images are absolute & crawlable — http:// often gets rejected
    # and crawlers fall back to the favicon/logo.
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "https")

    ALLOW_REGISTRATION = _as_bool(os.environ.get("ALLOW_REGISTRATION"), False)

    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@ahantapulse.online")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Atomic2@2020^")
    ADMIN_FORCE_RESET = _as_bool(os.environ.get("ADMIN_FORCE_RESET"), False)

    PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY", "")
    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_CURRENCY = os.environ.get("PAYSTACK_CURRENCY", "GHS")

    # ── AI writing assistant ──────────────────────────────────────────
    # Uses any OpenAI-compatible /chat/completions endpoint. Defaults to
    # DeepSeek (https://api.deepseek.com). The key can come from any of:
    #   AI_API_KEY, DEEPSEEK_API_KEY, OPENAI_API_KEY  (first one wins).
    AI_API_BASE = os.environ.get("AI_API_BASE", "https://api.deepseek.com/v1")
    AI_API_KEY = (
        os.environ.get("AI_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    )
    AI_MODEL = os.environ.get("AI_MODEL", "deepseek-chat")
    AI_MAX_TOKENS = int(os.environ.get("AI_MAX_TOKENS", "1800"))

    # ── TinyMCE Cloud (WYSIWYG editor) ────────────────────────────────
    # Override via env var TINYMCE_API_KEY when rotating.
    TINYMCE_API_KEY = os.environ.get(
        "TINYMCE_API_KEY",
        "ps3oq2yzvy43l968b2wgxtcegt0exfvjwv0hak1zqrkqszje",
    )

    # ── Google OAuth (Sign in with Google) ────────────────────────────
    # Admins can set these via Dashboard → Settings → Sign-in with Google,
    # or via env vars on platforms that prefer that. Leaving both blank
    # disables the Google sign-in flow site-wide.
    GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")

    WTF_CSRF_TIME_LIMIT = None
