"""Small helpers shared across blueprints.

Kept intentionally lightweight: slug generation, safe markdown rendering,
embed-URL detection for Facebook / YouTube / Vimeo / SoundCloud / Spotify,
upload sanitisation, and a role-based access decorator.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Iterable
from urllib.parse import quote, urlparse

import bleach
from bleach.css_sanitizer import CSSSanitizer
import markdown as md_lib
import requests
from flask import abort, current_app
from flask_login import current_user
from PIL import Image, ImageDraw, ImageFont
from slugify import slugify as _slugify
from werkzeug.utils import secure_filename


_ALLOWED_TAGS = sorted(
    set(bleach.sanitizer.ALLOWED_TAGS)
    | {
        "p", "pre", "h1", "h2", "h3", "h4", "h5", "h6",
        "br", "hr", "img", "figure", "figcaption",
        "table", "thead", "tbody", "tr", "th", "td",
        "span", "div", "s", "u", "iframe",
    }
)
_ALLOWED_ATTRS = {
    "*": ["class", "style"],
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "width", "height", "loading", "style"],
    "iframe": [
        "src", "width", "height", "frameborder", "allow",
        "allowfullscreen", "loading", "style",
    ],
}
# Only allow a small whitelist of style properties — the WYSIWYG editor
# emits these when the user resizes or aligns an image / iframe.
_CSS_SANITIZER = CSSSanitizer(allowed_css_properties=[
    "width", "height",
    "max-width", "max-height", "min-width", "min-height",
    "float", "clear",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "display", "text-align", "vertical-align",
])

# Quick check: does this look like HTML the editor produced (vs. plain markdown)?
_HTML_HINT = re.compile(r"<\s*(p|h[1-6]|ol|ul|blockquote|figure|table|div|br|hr|img)\b", re.I)


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
    """Render rich-text body to sanitised HTML for safe display.

    If `text` already looks like HTML (the WYSIWYG editor stores HTML), we just
    sanitise it. Otherwise we treat it as Markdown and convert first.
    """
    if not text:
        return ""
    if _HTML_HINT.search(text):
        html = text
    else:
        html = md_lib.markdown(
            text,
            extensions=["extra", "sane_lists", "nl2br", "tables", "fenced_code"],
            output_format="html",
        )
    cleaned = bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        css_sanitizer=_CSS_SANITIZER,
        strip=True,
    )
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


def cover_url(value: str | None, external: bool = False) -> str | None:
    """Resolve a stored image reference to a URL ready to use in `<img src>`.

    Storage values can be either:
      - a relative path inside the static folder (e.g. ``uploads/foo.jpg``), or
      - an absolute http(s) URL (e.g. an Unsplash photo).

    Absolute URLs pass through unchanged. Relative paths are resolved with
    Flask's ``url_for("static")``; pass ``external=True`` to receive an
    absolute URL (useful for OpenGraph meta tags).
    Returns ``None`` when nothing is set.
    """
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    if v.startswith(("http://", "https://", "//", "data:")):
        return v
    from flask import url_for
    return url_for("static", filename=v.lstrip("/"), _external=external)


def reading_time_minutes(text: str | None, wpm: int = 220) -> int:
    """Estimate reading time in minutes (minimum 1) for the given Markdown text."""
    if not text:
        return 1
    cleaned = bleach.clean(text, tags=[], strip=True)
    word_count = len(re.findall(r"\b\w+\b", cleaned))
    if word_count <= 0:
        return 1
    minutes = (word_count + wpm - 1) // wpm
    return max(1, minutes)


_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


def _load_watermark_font(size: int):
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size=size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def save_original_image(file_storage, *, subdir: str) -> tuple[str, str, int, int]:
    """Save the uploaded image as the *original* under instance/originals/<subdir>.

    Returns (relative_path, original_filename, width, height). The relative
    path is rooted at instance/originals/ — callers must combine it with the
    configured ORIGINALS_DIR to get an absolute path.
    """
    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise ValueError("No file supplied.")
    if not is_allowed(file_storage.filename, current_app.config["ALLOWED_IMAGE_EXT"]):
        raise ValueError(f"File type not allowed: {file_storage.filename}")

    originals_root = current_app.config.get("ORIGINALS_DIR")
    if not originals_root:
        raise RuntimeError("ORIGINALS_DIR is not configured.")
    originals_root = str(originals_root)

    now = datetime.now(timezone.utc)
    rel_dir = os.path.join(subdir, f"{now.year:04d}", f"{now.month:02d}")
    abs_dir = os.path.join(originals_root, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    safe_name = secure_filename(file_storage.filename) or "image"
    unique = f"{uuid.uuid4().hex[:12]}-{safe_name}"
    abs_path = os.path.join(abs_dir, unique)
    file_storage.save(abs_path)

    with Image.open(abs_path) as probe:
        width, height = probe.size

    rel_path = os.path.join(rel_dir, unique).replace(os.sep, "/")
    return rel_path, safe_name, width, height


def delete_original(rel_path: str | None) -> None:
    """Delete a private original file given its path relative to ORIGINALS_DIR."""
    if not rel_path:
        return
    originals_root = current_app.config.get("ORIGINALS_DIR")
    if not originals_root:
        return
    abs_path = os.path.join(str(originals_root), rel_path)
    try:
        if os.path.isfile(abs_path):
            os.remove(abs_path)
    except OSError:
        pass


def make_watermarked_preview(
    src_abs_path: str,
    *,
    subdir: str = "portraits",
    max_width: int = 1600,
    watermark_text: str = "AhantaPulse — preview",
) -> str:
    """Create a downsized, watermarked preview from a private original.

    Writes the result under static/uploads/<subdir>/<yyyy>/<mm>/ and returns
    the path relative to the static folder (suitable for url_for('static', ...)).
    """
    static_root = current_app.static_folder or "static"
    now = datetime.now(timezone.utc)
    rel_dir = os.path.join("uploads", subdir, f"{now.year:04d}", f"{now.month:02d}")
    abs_dir = os.path.join(static_root, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    name = f"{uuid.uuid4().hex[:12]}-preview.jpg"
    out_abs_path = os.path.join(abs_dir, name)

    with Image.open(src_abs_path) as img:
        img = img.convert("RGBA")
        if img.width > max_width:
            new_h = int(img.height * (max_width / img.width))
            img = img.resize((max_width, new_h), Image.LANCZOS)

        w, h = img.size
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))

        # Build a rotated text tile, then paste it across the canvas.
        font_size = max(28, w // 22)
        font = _load_watermark_font(font_size)
        bbox = font.getbbox(watermark_text)
        text_w = max(1, bbox[2] - bbox[0])
        text_h = max(1, bbox[3] - bbox[1])

        tile = Image.new("RGBA", (text_w + 60, text_h + 30), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text(
            (30, 15), watermark_text, font=font, fill=(255, 255, 255, 110)
        )
        tile = tile.rotate(-28, expand=True, resample=Image.BICUBIC)

        step_x = int(tile.width * 0.85)
        step_y = int(tile.height * 1.6)
        for y in range(-step_y, h + step_y, step_y):
            offset = (step_x // 2) if (y // step_y) % 2 else 0
            for x in range(-step_x + offset, w + step_x, step_x):
                overlay.paste(tile, (x, y), tile)

        result = Image.alpha_composite(img, overlay).convert("RGB")
        result.save(out_abs_path, "JPEG", quality=82, optimize=True)

    return os.path.join(rel_dir, name).replace(os.sep, "/")


PAYSTACK_API_BASE = "https://api.paystack.co"


def paystack_configured() -> bool:
    return bool(current_app.config.get("PAYSTACK_SECRET_KEY"))


def paystack_initialize(
    *,
    amount_pesewas: int,
    email: str,
    callback_url: str,
    reference: str,
    currency: str = "GHS",
    metadata: dict | None = None,
) -> dict:
    """Initialise a Paystack transaction. Returns the parsed JSON payload."""
    secret = current_app.config.get("PAYSTACK_SECRET_KEY")
    if not secret:
        raise RuntimeError("Paystack is not configured (missing PAYSTACK_SECRET_KEY).")
    payload = {
        "email": email,
        "amount": int(amount_pesewas),
        "currency": currency,
        "callback_url": callback_url,
        "reference": reference,
    }
    if metadata:
        payload["metadata"] = metadata
    resp = requests.post(
        f"{PAYSTACK_API_BASE}/transaction/initialize",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def paystack_verify(reference: str) -> dict:
    """Verify a Paystack transaction by reference. Returns the parsed JSON."""
    secret = current_app.config.get("PAYSTACK_SECRET_KEY")
    if not secret:
        raise RuntimeError("Paystack is not configured (missing PAYSTACK_SECRET_KEY).")
    resp = requests.get(
        f"{PAYSTACK_API_BASE}/transaction/verify/{reference}",
        headers={"Authorization": f"Bearer {secret}"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def verify_paystack_signature(body: bytes, signature: str | None) -> bool:
    """Verify the `x-paystack-signature` header for an incoming webhook."""
    if not signature:
        return False
    secret = (current_app.config.get("PAYSTACK_SECRET_KEY") or "").encode()
    if not secret:
        return False
    expected = hmac.new(secret, body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


def new_payment_reference(prefix: str = "AP") -> str:
    """Short, unique reference suitable for Paystack."""
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}"


def new_download_token() -> str:
    return secrets.token_urlsafe(32)


# ───────────────────────── AI writing assistant ─────────────────────────

def ai_configured() -> bool:
    return bool(current_app.config.get("AI_API_KEY"))


def _ai_chat(messages: list[dict], *, max_tokens: int | None = None, json_mode: bool = False) -> str:
    """Call an OpenAI-compatible chat-completions endpoint. Returns the raw text."""
    key = current_app.config.get("AI_API_KEY")
    if not key:
        raise RuntimeError("AI is not configured. Set AI_API_KEY (or OPENAI_API_KEY).")
    base = (current_app.config.get("AI_API_BASE") or "https://api.openai.com/v1").rstrip("/")
    model = current_app.config.get("AI_MODEL", "gpt-4o-mini")
    body: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": int(max_tokens or current_app.config.get("AI_MAX_TOKENS", 1800)),
        "temperature": 0.7,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    resp = requests.post(
        f"{base}/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=90,
    )
    if resp.status_code >= 400:
        # Surface the provider's error message to the caller for easier debugging.
        try:
            err = resp.json().get("error", {}).get("message") or resp.text
        except Exception:
            err = resp.text
        raise RuntimeError(f"AI provider error ({resp.status_code}): {err}")
    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    msg = (choice.get("message") or {}).get("content") or ""
    return msg.strip()


def _strip_code_fence(text: str) -> str:
    """If the model wrapped output in a ```html ... ``` fence, strip it."""
    t = text.strip()
    if t.startswith("```"):
        # remove leading fence
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1 :]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


_SYSTEM_NEWS = (
    "You are a senior news editor for AhantaPulse, a local news portal covering "
    "the Ahanta region of Ghana. You write clear, factual, balanced articles for "
    "a general audience. Prefer simple language, short paragraphs (2-4 sentences), "
    "subheadings, and active voice. Optimize for both readability and Google search "
    "without keyword-stuffing. Never invent facts about real people or events — if "
    "a specific name, date or quote is needed but not provided, leave a clearly "
    "marked placeholder like [SOURCE NEEDED] so the editor can fill it in."
)

_HTML_RULES = (
    "Output ONLY the article BODY as clean HTML, no <html>, <head> or <body> tags. "
    "Use these tags only: <h2>, <h3>, <p>, <ul>, <ol>, <li>, <blockquote>, <strong>, "
    "<em>, <a>. Do NOT output a top-level <h1> (the page already has the title). "
    "Do NOT wrap the output in code fences."
)


def ai_draft_article(brief: str) -> str:
    """Draft a full article body from a short brief. Returns HTML."""
    user = (
        "Write a complete news article based on this brief. Length 400-700 words. "
        "Open with a strong lead paragraph that includes the most relevant search "
        "keyword naturally. Use 2-4 H2 subheadings. Close with a short forward-looking "
        "or context paragraph.\n\n"
        f"Brief:\n{brief}\n\n" + _HTML_RULES
    )
    return _strip_code_fence(_ai_chat(
        [{"role": "system", "content": _SYSTEM_NEWS}, {"role": "user", "content": user}],
    ))


def ai_improve_article(html_or_text: str, focus_keyword: str | None = None) -> str:
    """Rewrite/improve the given article body. Returns HTML."""
    kw_line = f"\nPrimary keyword to weave in naturally: {focus_keyword}\n" if focus_keyword else ""
    user = (
        "Improve this article for readability AND Google search. Keep the meaning "
        "and facts unchanged. Tighten verbose sentences, add helpful H2/H3 "
        "subheadings if missing, and ensure the lead paragraph contains the main "
        "topic keyword. Do not invent facts.\n"
        f"{kw_line}\nArticle:\n{html_or_text}\n\n" + _HTML_RULES
    )
    return _strip_code_fence(_ai_chat(
        [{"role": "system", "content": _SYSTEM_NEWS}, {"role": "user", "content": user}],
    ))


def ai_seo_meta(html_or_text: str) -> dict:
    """Return {title_suggestions, summary, tags, focus_keyword} as JSON."""
    user = (
        "For the article below, output a JSON object exactly like:\n"
        "{\n"
        '  "summary": "A 1-2 sentence meta description, max 160 chars",\n'
        '  "focus_keyword": "the single most search-relevant phrase",\n'
        '  "tags": ["tag1", "tag2", "tag3"],   // 3-7 short tags, lowercase\n'
        '  "title_suggestions": ["headline 1", "headline 2", "headline 3"]\n'
        "}\n\n"
        "Tags should be short, lowercase, no hashtags. Title suggestions should be "
        "punchy and ≤ 70 chars each.\n\n"
        f"Article:\n{html_or_text}"
    )
    raw = _ai_chat(
        [{"role": "system", "content": _SYSTEM_NEWS}, {"role": "user", "content": user}],
        json_mode=True,
        max_tokens=600,
    )
    import json as _json
    try:
        return _json.loads(raw)
    except ValueError:
        # Some providers wrap JSON in fences even with response_format set.
        return _json.loads(_strip_code_fence(raw))


def parse_tags(raw: str | None) -> list[str]:
    """Split a comma- or hash-separated tag string into clean, deduplicated names."""
    if not raw:
        return []
    parts = re.split(r"[,#]", raw)
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        name = re.sub(r"\s+", " ", p).strip().strip("#").strip()
        if not name:
            continue
        if len(name) > 64:
            name = name[:64].rstrip()
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out
