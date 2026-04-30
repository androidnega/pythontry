"""
cPanel Phusion Passenger entry point.

Application startup file: passenger_wsgi.py
WSGI callable: application
"""

from __future__ import annotations

import os
import sys

# Application root = directory containing this file
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app import application  # noqa: E402
