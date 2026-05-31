"""AhantaPulse — Flask news portal (WSGI: `application`).

This module assembles the app: registers extensions and blueprints, seeds the
admin user and default categories on first run, and exposes a few CLI helpers.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from flask import Flask, render_template

from config import Config
from extensions import csrf, db, login_manager
from utils import excerpt, render_markdown


def create_app(config_object: type[Config] = Config) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Blueprints registered lazily to avoid circular imports.
    from blueprints.public import bp as public_bp
    from blueprints.auth import bp as auth_bp
    from blueprints.admin import bp as admin_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    app.jinja_env.filters["markdown"] = render_markdown
    app.jinja_env.filters["excerpt"] = excerpt

    @app.context_processor
    def inject_site() -> dict:
        return {
            "SITE_NAME": app.config["SITE_NAME"],
            "SITE_TAGLINE": app.config["SITE_TAGLINE"],
            "SITE_REGION": app.config["SITE_REGION"],
            "ALLOW_REGISTRATION": app.config["ALLOW_REGISTRATION"],
            "now_year": lambda: datetime.now(timezone.utc).year,
        }

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(_e):
        mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return (
            render_template("errors/413.html", limit_mb=mb),
            413,
        )

    @app.errorhandler(500)
    def server_error(_e):
        return render_template("errors/500.html"), 500

    @app.cli.command("init-db")
    def init_db_cmd() -> None:
        """Create tables and seed the admin user + default categories."""
        with app.app_context():
            initialise_database()
            print("Database initialised.")

    with app.app_context():
        try:
            initialise_database()
        except Exception as exc:  # don't crash WSGI boot on first deploy
            app.logger.warning("Skipping auto-init: %s", exc)

    return app


def initialise_database() -> None:
    """Create tables (idempotent) and seed an admin + default categories."""
    from models import Category, User  # local import to avoid circular ref

    db.create_all()

    admin_username = Config.ADMIN_USERNAME
    admin_email = Config.ADMIN_EMAIL
    admin_password = Config.ADMIN_PASSWORD

    admin = (
        db.session.query(User).filter_by(username=admin_username).first()
        if admin_username
        else None
    )
    if admin is None and admin_username and admin_password:
        admin = User(
            username=admin_username,
            email=admin_email,
            role=User.ROLE_ADMIN,
            display_name="Site admin",
        )
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()

    if db.session.query(Category).count() == 0:
        defaults = [
            ("Ahanta News", "news"),
            ("Politics", "news"),
            ("Culture & Heritage", "news"),
            ("Community", "news"),
            ("AhantaPulse Show", "video"),
            ("Music", "audio"),
            ("Marketplace", "ad"),
        ]
        from utils import slugify, unique_slug

        for name, kind in defaults:
            base = slugify(name)
            slug = unique_slug(
                base,
                lambda s: db.session.query(Category).filter_by(slug=s).first(),
            )
            db.session.add(Category(name=name, slug=slug, kind=kind))
        db.session.commit()


app = create_app()
application = app  # Passenger / WSGI entry
