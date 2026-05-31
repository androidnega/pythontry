"""Small helpers shared across blueprints.

Kept intentionally lightweight: slug generation, safe markdown rendering,
embed-URL detection for Facebook / YouTube / Vimeo / SoundCloud / Spotify,
upload sanitisation, and a role-based access decorator.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Iterable
from urllib.parse import quote, urlparse

import bleach
import markdown as md_lib
from flask import abort, current_app
from flask_login import current_user
from slugify import slugify as _slugify
from werkzeug.utils import secure_filename


_ALLOWED_TAGS = sorted(
    set(bleach.sanitizer.ALLOWED_TAGS)
    | {
        "p", "pre", "h1", "h2", "h3", "h4", "h5", "h6",
        "br", "hr", "img", "figure", "figcaption",
        "table", "thead", "tbody", "tr", "th", "td",
        "span", "div",
    }
)
_ALLOWED_ATTRS = {
    "*": ["class"],
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "width", "height", "loading"],
}


def slugify(value: str, *, max_length: int = 120) -> str:
    base = _slugify(value or "", max_length=max_length) or uuid.uuid4().hex[:10]
    return base


def unique_slug(base: str, exists_query) -> str:
    """Return a slug guaranteed unique by appending -2, -3 ... if needed.

    `exists_query` is a callable taking a candidate slug and returning a
    truthy result (e.g. a SQLAlchemy row) when that slug is already taken.
    """
    candidate = base
    n = 2
    while exists_query(candidate):
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def render_markdown(text: str | None) -> str:
    """Render markdown to sanitised HTML for safe display."""
    if not text:
        return ""
    html = md_lib.markdown(
        text,
        extensions=["extra", "sane_lists", "nl2br", "tables", "fenced_code"],
        output_format="html",
    )
    cleaned = bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)
    return bleach.linkify(cleaned)


_YT_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/|v/)|youtu\.be/)([\w-]{6,})",
    re.IGNORECASE,
)
_VIMEO_RE = re.compile(r"vimeo\.com/(?:video/)?(\d+)", re.IGNORECASE)
_FB_VIDEO_RE = re.compile(r"(facebook\.com|fb\.watch)/", re.IGNORECASE)
_SC_RE = re.compile(r"soundcloud\.com/", re.IGNORECASE)
_SPOTIFY_RE = re.compile(
    r"open\.spotify\.com/(track|episode|show|playlist|album)/([A-Za-z0-9]+)",
    re.IGNORECASE,
)


def detect_embed(url: str | None) -> dict | None:
    """Return a dict describing an embeddable player for `url`, or None.

    Result shape: {"provider", "src", "kind": "video"|"audio", "aspect"}
    `aspect` is a CSS aspect-ratio string (e.g. "16 / 9") or None for fixed-height
    embeds like SoundCloud.
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None

    m = _YT_RE.search(url)
    if m:
        return {
            "provider": "youtube",
            "src": f"https://www.youtube.com/embed/{m.group(1)}",
            "kind": "video",
            "aspect": "16 / 9",
        }

    m = _VIMEO_RE.search(url)
    if m:
        return {
            "provider": "vimeo",
            "src": f"https://player.vimeo.com/video/{m.group(1)}",
            "kind": "video",
            "aspect": "16 / 9",
        }

    m = _SPOTIFY_RE.search(url)
    if m:
        kind = "audio"
        return {
            "provider": "spotify",
            "src": f"https://open.spotify.com/embed/{m.group(1)}/{m.group(2)}",
            "kind": kind,
            "aspect": None,
            "fixed_height": 232 if m.group(1) in {"track"} else 352,
        }

    if _FB_VIDEO_RE.search(url):
        encoded = quote(url, safe="")
        return {
            "provider": "facebook",
            "src": (
                "https://www.facebook.com/plugins/video.php?"
                f"href={encoded}&show_text=false&autoplay=false"
            ),
            "kind": "video",
            "aspect": "16 / 9",
        }

    if _SC_RE.search(url):
        encoded = quote(url, safe="")
        return {
            "provider": "soundcloud",
            "src": (
                "https://w.soundcloud.com/player/?url="
                f"{encoded}&color=%23ff5500&auto_play=false&hide_related=false"
                "&show_comments=true&show_user=true&show_reposts=false&show_teaser=true"
            ),
            "kind": "audio",
            "aspect": None,
            "fixed_height": 166,
        }

    parsed = urlparse(url)
    return {
        "provider": "link",
        "src": url,
        "kind": None,
        "aspect": None,
        "host": parsed.netloc or url,
    }


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def is_allowed(filename: str, allowed: Iterable[str]) -> bool:
    return _ext(filename) in {a.lower() for a in allowed}


def save_upload(file_storage, *, subdir: str, allowed: Iterable[str]) -> str | None:
    """Persist a Werkzeug FileStorage under static/uploads/<subdir>/<yyyy>/<mm>/.

    Returns the path relative to the `static/` folder (suitable for
    url_for('static', filename=...)) or None when no file was supplied.
    """
    if file_storage is None or not getattr(file_storage, "filename", ""):
        return None
    if not is_allowed(file_storage.filename, allowed):
        raise ValueError(f"File type not allowed: {file_storage.filename}")

    now = datetime.now(timezone.utc)
    rel_dir = os.path.join("uploads", subdir, f"{now.year:04d}", f"{now.month:02d}")
    abs_dir = os.path.join(current_app.static_folder or "static", rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    safe_name = secure_filename(file_storage.filename) or "file"
    unique = f"{uuid.uuid4().hex[:10]}-{safe_name}"
    abs_path = os.path.join(abs_dir, unique)
    file_storage.save(abs_path)
    return os.path.join(rel_dir, unique).replace(os.sep, "/")


def delete_upload(rel_path: str | None) -> None:
    """Delete an uploaded file given a path relative to `static/`."""
    if not rel_path:
        return
    base = current_app.static_folder or "static"
    abs_path = os.path.join(base, rel_path)
    try:
        if os.path.isfile(abs_path):
            os.remove(abs_path)
    except OSError:
        pass


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def login_or_403(view):
    """Like @login_required but returns 403 instead of redirecting (for JSON-ish flows)."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def can_edit(obj) -> bool:
    """Owner-or-admin check for content rows that have an `author_id`."""
    if not current_user.is_authenticated:
        return False
    if current_user.is_admin:
        return True
    return getattr(obj, "author_id", None) == current_user.id


def excerpt(text: str | None, limit: int = 180) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", bleach.clean(text, tags=[], strip=True)).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "\u2026"
