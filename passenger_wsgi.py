"""
cPanel Phusion Passenger entry point.

Application startup file: passenger_wsgi.py
WSGI callable: application
"""

from __future__ import annotations

import os
import sys
import traceback

# Application root = directory containing this file
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# tmp/ already exists for the restart.txt trick — reuse it for crash logs
_LOG_DIR = os.path.join(_ROOT, "tmp")
try:
    os.makedirs(_LOG_DIR, exist_ok=True)
except Exception:
    _LOG_DIR = _ROOT


def _log_crash(exc: BaseException) -> None:
    """Best-effort: dump the traceback to tmp/passenger.log so the cause
    of a failed app boot is visible without having to chase stderr."""
    try:
        with open(os.path.join(_LOG_DIR, "passenger.log"), "a") as fh:
            fh.write("\n--- passenger boot error ---\n")
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=fh)
    except Exception:
        pass


def _fallback_app(environ, start_response):
    """Tiny WSGI app served when the real app can't be imported.
    Returns a 503 with a short hint — never reveals stack traces to
    visitors. Server admin checks tmp/passenger.log for the real cause."""
    msg = (
        b"<!doctype html><meta charset=utf-8><title>Service unavailable</title>"
        b"<style>body{font-family:system-ui;padding:48px;max-width:640px;margin:auto}"
        b"h1{font-weight:700}p{color:#475569;line-height:1.55}code{background:#f1f5f9;"
        b"padding:2px 6px;border-radius:4px}</style>"
        b"<h1>We're updating the site.</h1>"
        b"<p>Please refresh in a moment. If you're the administrator, see "
        b"<code>tmp/passenger.log</code> for details.</p>"
    )
    start_response(
        "503 Service Unavailable",
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(msg))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [msg]


try:
    from app import application  # noqa: E402
except BaseException as _boot_err:  # pragma: no cover
    _log_crash(_boot_err)
    application = _fallback_app  # noqa: F811 — intentional fallback
