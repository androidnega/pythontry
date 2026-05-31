"""Shared Flask extensions instantiated once and bound in the app factory."""

from __future__ import annotations

from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"
login_manager.login_message = "Please sign in to continue."
