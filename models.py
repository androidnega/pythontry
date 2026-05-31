"""Database models for the AhantaPulse news portal.

Single-file model module keeps the surface area small and easy to scan.
Relationships are declared with SQLAlchemy 2.x typed mappings, but we keep the
column declarations old-style for compatibility with Flask-SQLAlchemy's `Model`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, login_manager


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    ROLE_ADMIN = "admin"
    ROLE_WRITER = "writer"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default=ROLE_WRITER)
    display_name = db.Column(db.String(120))
    bio = db.Column(db.Text)
    avatar_path = db.Column(db.String(255))
    is_active_flag = db.Column("is_active", db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    articles = db.relationship("Article", back_populates="author", lazy="dynamic")
    media_items = db.relationship("MediaItem", back_populates="author", lazy="dynamic")
    ads = db.relationship("Ad", back_populates="author", lazy="dynamic")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == self.ROLE_ADMIN

    @property
    def is_active(self) -> bool:  # Flask-Login hook
        return bool(self.is_active_flag)

    @property
    def name(self) -> str:
        return self.display_name or self.username

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


@login_manager.user_loader
def _load_user(user_id: str):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


class Category(db.Model):
    __tablename__ = "categories"

    KIND_NEWS = "news"
    KIND_VIDEO = "video"
    KIND_AUDIO = "audio"
    KIND_AD = "ad"
    KIND_ALL = "all"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False, index=True)
    kind = db.Column(db.String(16), nullable=False, default=KIND_ALL)
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    articles = db.relationship("Article", back_populates="category", lazy="dynamic")
    media_items = db.relationship("MediaItem", back_populates="category", lazy="dynamic")
    ads = db.relationship("Ad", back_populates="category", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Category {self.name} ({self.kind})>"


article_tags = db.Table(
    "article_tags",
    db.Column("article_id", db.Integer, db.ForeignKey("articles.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), primary_key=True),
)


class Tag(db.Model):
    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    articles = db.relationship("Article", secondary=article_tags, back_populates="tags")

    def __repr__(self) -> str:
        return f"<Tag {self.slug!r}>"


class Article(db.Model):
    __tablename__ = "articles"

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(280), unique=True, nullable=False, index=True)
    summary = db.Column(db.String(500))
    body = db.Column(db.Text, nullable=False, default="")
    cover_image = db.Column(db.String(255))
    status = db.Column(db.String(16), nullable=False, default=STATUS_DRAFT)
    is_featured = db.Column(db.Boolean, default=False, nullable=False)
    view_count = db.Column(db.Integer, default=0, nullable=False)

    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    published_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    category = db.relationship("Category", back_populates="articles")
    author = db.relationship("User", back_populates="articles")
    tags = db.relationship("Tag", secondary=article_tags, back_populates="articles")

    @property
    def is_published(self) -> bool:
        return self.status == self.STATUS_PUBLISHED

    def __repr__(self) -> str:
        return f"<Article {self.slug!r}>"


class MediaItem(db.Model):
    """A video or audio item, either embedded from a URL or uploaded."""

    __tablename__ = "media_items"

    KIND_VIDEO = "video"
    KIND_AUDIO = "audio"

    SOURCE_EMBED = "embed"
    SOURCE_UPLOAD = "upload"

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(280), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    kind = db.Column(db.String(16), nullable=False)
    source_type = db.Column(db.String(16), nullable=False)
    embed_url = db.Column(db.String(1024))
    file_path = db.Column(db.String(512))
    thumbnail_path = db.Column(db.String(512))
    status = db.Column(db.String(16), nullable=False, default=STATUS_PUBLISHED)
    is_featured = db.Column(db.Boolean, default=False, nullable=False)
    view_count = db.Column(db.Integer, default=0, nullable=False)

    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    category = db.relationship("Category", back_populates="media_items")
    author = db.relationship("User", back_populates="media_items")

    @property
    def is_published(self) -> bool:
        return self.status == self.STATUS_PUBLISHED

    @property
    def is_embed(self) -> bool:
        return self.source_type == self.SOURCE_EMBED

    def __repr__(self) -> str:
        return f"<MediaItem {self.slug!r} kind={self.kind}>"


class Ad(db.Model):
    """A product or service advertisement / marketplace listing."""

    __tablename__ = "ads"

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(280), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    price = db.Column(db.String(64))
    currency = db.Column(db.String(8), default="GHS")
    contact_phone = db.Column(db.String(64))
    contact_email = db.Column(db.String(255))
    contact_whatsapp = db.Column(db.String(64))
    location = db.Column(db.String(120))
    image_path = db.Column(db.String(512))
    external_url = db.Column(db.String(512))
    status = db.Column(db.String(16), nullable=False, default=STATUS_PUBLISHED)
    is_featured = db.Column(db.Boolean, default=False, nullable=False)
    view_count = db.Column(db.Integer, default=0, nullable=False)

    expires_at = db.Column(db.DateTime)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    category = db.relationship("Category", back_populates="ads")
    author = db.relationship("User", back_populates="ads")

    @property
    def is_published(self) -> bool:
        return self.status == self.STATUS_PUBLISHED

    def __repr__(self) -> str:
        return f"<Ad {self.slug!r}>"


class NotifySignup(db.Model):
    __tablename__ = "notify_signups"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<NotifySignup {self.email}>"
