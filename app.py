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
from utils import cover_url, excerpt, render_markdown


def create_app(config_object: type[Config] = Config) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["ORIGINALS_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Blueprints registered lazily to avoid circular imports.
    from blueprints.public import bp as public_bp
    from blueprints.auth import bp as auth_bp
    from blueprints.admin import bp as admin_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/dashboard")

    app.jinja_env.filters["markdown"] = render_markdown
    app.jinja_env.filters["excerpt"] = excerpt
    app.jinja_env.filters["cover_url"] = cover_url
    app.jinja_env.globals["cover_url"] = cover_url

    @app.context_processor
    def inject_site() -> dict:
        return {
            "SITE_NAME": app.config["SITE_NAME"],
            "SITE_SLOGAN": app.config["SITE_SLOGAN"],
            "SITE_TAGLINE": app.config["SITE_TAGLINE"],
            "SITE_REGION": app.config["SITE_REGION"],
            "ALLOW_REGISTRATION": app.config["ALLOW_REGISTRATION"],
            "TINYMCE_API_KEY": _safe_tinymce_key(),
            "ASSET_VERSION": _asset_version(),
            "now_year": lambda: datetime.now(timezone.utc).year,
        }

    def _safe_tinymce_key() -> str:
        from utils import get_tinymce_key
        try:
            return get_tinymce_key()
        except Exception:
            return app.config.get("TINYMCE_API_KEY", "") or ""

    # mtime-based version string so CSS/JS updates bust the browser cache
    # without manual deploy steps. Computed once per process start.
    _ASSET_VERSION_CACHE = {}

    def _asset_version() -> str:
        if "v" in _ASSET_VERSION_CACHE:
            return _ASSET_VERSION_CACHE["v"]
        try:
            css_path = os.path.join(app.static_folder, "css", "theme.css")
            mtime = int(os.path.getmtime(css_path))
        except OSError:
            mtime = 0
        v = str(mtime or int(datetime.now(timezone.utc).timestamp()))
        _ASSET_VERSION_CACHE["v"] = v
        return v

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

    @app.cli.command("reset-admin")
    def reset_admin_cmd() -> None:
        """Reset the admin user's password and email to the values in env vars."""
        with app.app_context():
            from models import User

            admin = User.query.filter_by(username=Config.ADMIN_USERNAME).first()
            if admin is None:
                print(
                    f"No user named {Config.ADMIN_USERNAME!r} exists yet. "
                    "Run `flask init-db` first."
                )
                return
            admin.email = Config.ADMIN_EMAIL
            admin.role = User.ROLE_ADMIN
            admin.is_active_flag = True
            admin.set_password(Config.ADMIN_PASSWORD)
            db.session.commit()
            print(f"Admin {admin.username!r} reset (email + password + role).")

    @app.cli.command("seed-demo")
    def seed_demo_cmd() -> None:
        """Populate the database with a small set of demo news articles.

        Idempotent: skips articles whose slugs already exist. Existing
        content is never modified or removed.
        """
        with app.app_context():
            n = seed_demo_articles()
            if n == 0:
                print("No new demo articles added (all already present).")
            else:
                print(f"Seeded {n} demo article(s).")

    @app.cli.command("unseed-demo")
    def unseed_demo_cmd() -> None:
        """Remove articles created by `flask seed-demo` (by slug)."""
        with app.app_context():
            n = remove_demo_articles()
            print(f"Removed {n} demo article(s).")

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
    _apply_lightweight_migrations()

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
    elif admin and Config.ADMIN_FORCE_RESET and admin_password:
        admin.email = admin_email
        admin.role = User.ROLE_ADMIN
        admin.is_active_flag = True
        admin.set_password(admin_password)
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


_DEMO_ARTICLES: tuple[dict, ...] = (
    {
        "slug": "ahanta-cultural-festival-2026",
        "title": "Ahanta Cultural Festival returns to Busua with a sea of colour",
        "summary": (
            "Drummers, weavers and storytellers gathered along the Busua "
            "shoreline this weekend for the biggest edition of the festival "
            "in a decade."
        ),
        "category": "Culture & Heritage",
        "featured": True,
        "days_ago": 1,
        "tags": ["busua", "festival", "culture"],
        "cover_image": "https://images.unsplash.com/photo-1547499678-e02a8df5c3ee?auto=format&fit=crop&w=1600&q=80",
        "body": (
            "## A festival rooted in memory\n\n"
            "From the first beats of the **fontomfrom** at dawn to the late-"
            "night procession of the Asafo companies, this year's Ahanta "
            "Cultural Festival was a reminder of why the coast remembers.\n\n"
            "Chief Nana Kwaku Acquah, who opened the weekend, said the "
            "festival is \"more than a celebration — it is a school for the "
            "young to understand where we come from.\"\n\n"
            "### What's new this year\n\n"
            "- A children's **kente weaving** corner attracted more than 80 "
            "  pupils from Dixcove and Busua basic schools.\n"
            "- The maiden **Ahanta language spelling bee** crowned 11-year-"
            "  old Akua Mensah as the inaugural champion.\n"
            "- Local restaurants ran a *taste of Ahanta* tour featuring "
            "  smoked tuna, kontomire stew and palm-wine cocktails.\n\n"
            "> \"We want the festival to feel like a homecoming for every "
            "> child of the Ahanta, wherever they are now,\" said co-"
            "> organiser Esi Bonsu.\n\n"
            "The closing fireworks lit the bay just past 10pm. Planning for "
            "next year's edition begins in September."
        ),
    },
    {
        "slug": "dixcove-fishing-harbour-upgrade",
        "title": "Dixcove fishing harbour set for a long-awaited upgrade",
        "summary": (
            "A GHS 28 million project will modernise the landing site, add a "
            "cold store and pave the access road that fishers have lobbied "
            "for since 2017."
        ),
        "category": "Ahanta News",
        "featured": True,
        "days_ago": 2,
        "tags": ["dixcove", "infrastructure", "fishing"],
        "cover_image": "https://images.unsplash.com/photo-1559825481-12a05cc00344?auto=format&fit=crop&w=1600&q=80",
        "body": (
            "Work begins next month on the long-overdue upgrade of the "
            "Dixcove fishing harbour, after the Ministry of Roads signed "
            "off on the contractor's scope at the weekend.\n\n"
            "The package covers three things fishermen have asked for "
            "repeatedly:\n\n"
            "1. A **resurfaced jetty** with proper drainage so canoes can "
            "land safely at high tide.\n"
            "2. A **cold-storage block** big enough to hold a day's catch "
            "during the lean season.\n"
            "3. Paving of the **access road** from the highway to the "
            "harbour gate — currently a stretch that becomes impassable "
            "after heavy rain.\n\n"
            "Local fishmonger leader Madam Adwoa Sika welcomed the news but "
            "warned that the timing matters: \"Start it now and finish "
            "before the August upwelling. If we lose another season to "
            "construction, that is bad news for the women here.\""
        ),
    },
    {
        "slug": "ahanta-youth-coding-bootcamp",
        "title": "Ahanta youth coding bootcamp graduates first 40 students",
        "summary": (
            "Three months, two web apps and one big leap: meet the trainees "
            "who turned their first lines of Python into real, working "
            "community tools."
        ),
        "category": "Community",
        "featured": True,
        "days_ago": 4,
        "tags": ["education", "youth", "technology"],
        "cover_image": "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?auto=format&fit=crop&w=1600&q=80",
        "body": (
            "Forty young people from Agona Nkwanta, Princess Town and "
            "Apowa walked out of the Ahanta Youth Coding Bootcamp last "
            "Friday with certificates in one hand and live URLs in the "
            "other.\n\n"
            "Each trainee spent the final month working on a small "
            "community project. Highlights:\n\n"
            "- A **market price tracker** showing daily prices for tomato, "
            "  onion and pepper across three local markets.\n"
            "- A **lost-and-found board** for the central Agona Nkwanta "
            "  lorry station.\n"
            "- An **immunisation reminder bot** that sends SMS nudges to "
            "  parents two days before clinic days.\n\n"
            "Programme lead Kwesi Ofori said the next cohort opens in "
            "August and will double the number of laptops on the floor "
            "thanks to a partnership with a Takoradi-based ISP."
        ),
    },
    {
        "slug": "busua-beach-cleanup-record",
        "title": "Busua beach cleanup pulls a record 1.2 tonnes from the shoreline",
        "summary": (
            "More than 300 volunteers turned up at sunrise. By noon they had "
            "filled 84 sacks — most of it single-use plastic."
        ),
        "category": "Community",
        "featured": False,
        "days_ago": 5,
        "tags": ["environment", "busua", "community"],
        "cover_image": "https://images.unsplash.com/photo-1618477462146-050d2767eac4?auto=format&fit=crop&w=1600&q=80",
        "body": (
            "The largest single-day cleanup ever organised at Busua beach "
            "wrapped up at noon on Saturday with **1,212 kilograms** of "
            "waste removed from the shoreline.\n\n"
            "Organiser Ato Quayson said the haul confirms what fishermen "
            "have said for years: \"The tide brings the plastic right back "
            "every dry season. We can keep cleaning, but the real fix is "
            "stopping it upstream.\"\n\n"
            "The cleanup is now slated to run every two months until the "
            "end of the year."
        ),
    },
    {
        "slug": "princess-town-fort-restoration",
        "title": "Princess Town's 17th-century fort gets a careful new life",
        "summary": (
            "A team of conservators is rebuilding the seaward wall using "
            "the same lime mortar recipe the original Brandenburgers used."
        ),
        "category": "Culture & Heritage",
        "featured": False,
        "days_ago": 7,
        "tags": ["heritage", "princess-town", "tourism"],
        "cover_image": "https://images.unsplash.com/photo-1602513985279-e436b89ee9af?auto=format&fit=crop&w=1600&q=80",
        "body": (
            "On a quiet bluff overlooking the Atlantic, the small "
            "Brandenburg fort at Princess Town is getting the most careful "
            "restoration of its 340-year history.\n\n"
            "The team has spent six weeks documenting every stone before "
            "lifting any of it. The new lime mortar is mixed on-site from "
            "shell-lime collected along the coast, exactly as the original "
            "builders did.\n\n"
            "Chief conservator Naa Densu Owusu says the goal is not to "
            "make the fort look new: \"We want to stabilise what is here "
            "so the next generation can still walk these walls. Repair, "
            "not replace.\"\n\n"
            "The site will reopen to the public in October."
        ),
    },
    {
        "slug": "ahanta-pulse-podcast-launch",
        "title": "AhantaPulse launches a weekly podcast hosted in Fanti and English",
        "summary": (
            "Twenty-minute episodes every Thursday, with deep interviews "
            "from chiefs to fishmongers to first-year university students."
        ),
        "category": "Community",
        "cover_image": "https://images.unsplash.com/photo-1581368135153-a506cf13b1e1?auto=format&fit=crop&w=1600&q=80",
        "featured": False,
        "days_ago": 9,
        "tags": ["podcast", "media"],
        "body": (
            "Our team is excited to share that the **AhantaPulse Podcast** "
            "is now live. Episode 1 sits down with elder Nana Egya Boampong "
            "on what the *Kwesi nsia* festival means in 2026.\n\n"
            "Episodes drop every Thursday at 6pm GMT on Spotify, Apple "
            "Podcasts, and right here on the site. Have someone we should "
            "interview? Send the name to **tips@ahantapulse.online**."
        ),
    },
    {
        "slug": "agona-nkwanta-market-day-fire",
        "title": "Agona Nkwanta market traders count losses after Sunday fire",
        "summary": (
            "Twenty-two stalls were destroyed. No injuries, but several "
            "families lost a full season of inventory."
        ),
        "category": "Ahanta News",
        "featured": False,
        "days_ago": 11,
        "tags": ["agona-nkwanta", "safety"],
        "cover_image": "https://images.unsplash.com/photo-1605792657660-596af9009e82?auto=format&fit=crop&w=1600&q=80",
        "body": (
            "A fire that broke out shortly before midnight on Sunday "
            "destroyed twenty-two stalls in the eastern wing of the Agona "
            "Nkwanta market. Firefighters from Takoradi reached the scene "
            "in 38 minutes and contained the blaze before it spread to the "
            "main lorry park.\n\n"
            "The Ahanta West Municipal Assembly has set up a temporary "
            "registration desk for affected traders. The cause of the fire "
            "is still under investigation; an electrical fault is suspected."
        ),
    },
)


def seed_demo_articles() -> int:
    """Create demo articles defined in `_DEMO_ARTICLES`. Returns the count
    of articles actually inserted. Idempotent — articles whose slug already
    exists in the DB are skipped.
    """
    from datetime import datetime, timedelta, timezone

    from models import Article, Category, Tag, User
    from utils import slugify

    admin = (
        db.session.query(User).filter_by(username=Config.ADMIN_USERNAME).first()
        or db.session.query(User).filter_by(role=User.ROLE_ADMIN).first()
        or db.session.query(User).order_by(User.id.asc()).first()
    )
    if admin is None:
        print("No user found in the database. Run `flask init-db` first.")
        return 0

    created = 0
    backfilled = 0
    for spec in _DEMO_ARTICLES:
        existing = db.session.query(Article).filter_by(slug=spec["slug"]).first()
        if existing is not None:
            # Idempotent re-run: leave existing rows alone except for
            # filling in a missing cover image so older demo seeds get
            # picked up automatically next deploy.
            if not existing.cover_image and spec.get("cover_image"):
                existing.cover_image = spec["cover_image"]
                backfilled += 1
            continue

        category = (
            db.session.query(Category)
            .filter_by(name=spec.get("category", ""), kind=Category.KIND_NEWS)
            .first()
        )

        published_at = datetime.now(timezone.utc) - timedelta(
            days=int(spec.get("days_ago", 0))
        )

        article = Article(
            slug=spec["slug"],
            title=spec["title"],
            summary=spec.get("summary"),
            body=spec["body"],
            cover_image=spec.get("cover_image"),
            status=Article.STATUS_PUBLISHED,
            is_featured=bool(spec.get("featured")),
            category_id=category.id if category else None,
            author_id=admin.id,
            published_at=published_at,
            view_count=0,
        )
        db.session.add(article)

        with db.session.no_autoflush:
            for tag_label in spec.get("tags", []):
                tag_slug = slugify(tag_label)
                tag = db.session.query(Tag).filter_by(slug=tag_slug).first()
                if tag is None:
                    tag = Tag(name=tag_label.replace("-", " ").title(), slug=tag_slug)
                    db.session.add(tag)
                article.tags.append(tag)
        created += 1

    if created or backfilled:
        db.session.commit()
        if backfilled:
            print(f"Backfilled cover images on {backfilled} existing demo article(s).")
    return created


def remove_demo_articles() -> int:
    """Delete articles whose slugs are in the demo set. Returns count removed."""
    from models import Article

    slugs = [spec["slug"] for spec in _DEMO_ARTICLES]
    rows = db.session.query(Article).filter(Article.slug.in_(slugs)).all()
    n = 0
    for row in rows:
        db.session.delete(row)
        n += 1
    if n:
        db.session.commit()
    return n


def _apply_lightweight_migrations() -> None:
    """Add missing columns to existing tables (SQLite-friendly).

    `db.create_all()` only creates *missing* tables — it never ALTERs an
    existing one. Production databases that pre-date a model change need
    those new columns added or the app crashes on the next read.

    We keep this list small and forward-only. Each entry is idempotent.
    """
    from sqlalchemy import inspect, text

    bind = db.session.get_bind()
    insp = inspect(bind)

    def _add_columns(table: str, additions: list[tuple[str, str]]) -> None:
        if not insp.has_table(table):
            return
        existing = {c["name"] for c in insp.get_columns(table)}
        for name, sql_type in additions:
            if name in existing:
                continue
            try:
                db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
                db.session.commit()
            except Exception:
                db.session.rollback()

    _add_columns("portraits", [
        ("card_aspect", "VARCHAR(16) NOT NULL DEFAULT 'natural'"),
        ("focal_x", "INTEGER NOT NULL DEFAULT 50"),
        ("focal_y", "INTEGER NOT NULL DEFAULT 50"),
    ])
    _add_columns("notify_signups", [
        ("unsubscribe_token", "VARCHAR(64)"),
        ("unsubscribed_at",   "DATETIME"),
    ])

    # Backfill unsubscribe_token for existing rows that don't have one yet.
    if insp.has_table("notify_signups"):
        from models import NotifySignup
        import secrets
        rows = NotifySignup.query.filter(
            (NotifySignup.unsubscribe_token.is_(None))
            | (NotifySignup.unsubscribe_token == "")
        ).all()
        for r in rows:
            r.unsubscribe_token = secrets.token_urlsafe(24)
        if rows:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()


app = create_app()
application = app  # Passenger / WSGI entry
