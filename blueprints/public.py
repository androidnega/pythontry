"""Public-facing routes: homepage, news, videos, audio, ads, search, about."""

from __future__ import annotations

from flask import Blueprint, abort, jsonify, render_template, request
from sqlalchemy import or_

from extensions import db
from models import Ad, Article, Category, MediaItem, NotifySignup
from utils import detect_embed

bp = Blueprint("public", __name__)

PAGE_SIZE = 12


def _paginate(query, page: int, per_page: int = PAGE_SIZE):
    page = max(int(page or 1), 1)
    return query.paginate(page=page, per_page=per_page, error_out=False)


def _featured_articles(limit: int = 3):
    return (
        Article.query.filter_by(status=Article.STATUS_PUBLISHED, is_featured=True)
        .order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
        .limit(limit)
        .all()
    )


def _latest_articles(limit: int = 9, exclude_ids: list[int] | None = None):
    q = Article.query.filter_by(status=Article.STATUS_PUBLISHED)
    if exclude_ids:
        q = q.filter(~Article.id.in_(exclude_ids))
    return (
        q.order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
        .limit(limit)
        .all()
    )


def _latest_media(kind: str | None = None, limit: int = 6):
    q = MediaItem.query.filter_by(status=MediaItem.STATUS_PUBLISHED)
    if kind:
        q = q.filter_by(kind=kind)
    return q.order_by(MediaItem.created_at.desc()).limit(limit).all()


def _latest_ads(limit: int = 6):
    return (
        Ad.query.filter_by(status=Ad.STATUS_PUBLISHED)
        .order_by(Ad.is_featured.desc(), Ad.created_at.desc())
        .limit(limit)
        .all()
    )


def _categories(kind: str | None = None):
    q = Category.query
    if kind:
        q = q.filter(or_(Category.kind == kind, Category.kind == "all"))
    return q.order_by(Category.name).all()


@bp.app_template_filter("embed")
def _embed_filter(url):
    return detect_embed(url)


@bp.route("/")
def home():
    featured = _featured_articles(limit=3)
    exclude = [a.id for a in featured]
    latest = _latest_articles(limit=8, exclude_ids=exclude)
    return render_template(
        "home.html",
        featured=featured,
        latest=latest,
        videos=_latest_media(kind=MediaItem.KIND_VIDEO, limit=4),
        audios=_latest_media(kind=MediaItem.KIND_AUDIO, limit=3),
        ads=_latest_ads(limit=4),
        categories=_categories(kind="news"),
    )


@bp.route("/news")
def news_list():
    page = request.args.get("page", 1, type=int)
    category_slug = request.args.get("category")
    q = Article.query.filter_by(status=Article.STATUS_PUBLISHED)
    active_category = None
    if category_slug:
        active_category = Category.query.filter_by(slug=category_slug).first_or_404()
        q = q.filter_by(category_id=active_category.id)
    q = q.order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
    pagination = _paginate(q, page)
    return render_template(
        "news_list.html",
        pagination=pagination,
        articles=pagination.items,
        categories=_categories(kind="news"),
        active_category=active_category,
    )


@bp.route("/news/<slug>")
def article_detail(slug: str):
    article = Article.query.filter_by(slug=slug).first_or_404()
    if not article.is_published:
        abort(404)
    article.view_count = (article.view_count or 0) + 1
    db.session.commit()
    related = (
        Article.query.filter(
            Article.id != article.id,
            Article.status == Article.STATUS_PUBLISHED,
            Article.category_id == article.category_id,
        )
        .order_by(Article.created_at.desc())
        .limit(3)
        .all()
    )
    return render_template("article_detail.html", article=article, related=related)


@bp.route("/videos")
def videos_list():
    page = request.args.get("page", 1, type=int)
    category_slug = request.args.get("category")
    q = MediaItem.query.filter_by(
        status=MediaItem.STATUS_PUBLISHED, kind=MediaItem.KIND_VIDEO
    )
    active_category = None
    if category_slug:
        active_category = Category.query.filter_by(slug=category_slug).first_or_404()
        q = q.filter_by(category_id=active_category.id)
    q = q.order_by(MediaItem.created_at.desc())
    pagination = _paginate(q, page)
    return render_template(
        "media_list.html",
        kind="video",
        title="Videos",
        pagination=pagination,
        items=pagination.items,
        categories=_categories(kind="video"),
        active_category=active_category,
    )


@bp.route("/videos/<slug>")
def video_detail(slug: str):
    item = MediaItem.query.filter_by(slug=slug, kind=MediaItem.KIND_VIDEO).first_or_404()
    if not item.is_published:
        abort(404)
    item.view_count = (item.view_count or 0) + 1
    db.session.commit()
    return render_template("media_detail.html", item=item)


@bp.route("/audio")
def audio_list():
    page = request.args.get("page", 1, type=int)
    category_slug = request.args.get("category")
    q = MediaItem.query.filter_by(
        status=MediaItem.STATUS_PUBLISHED, kind=MediaItem.KIND_AUDIO
    )
    active_category = None
    if category_slug:
        active_category = Category.query.filter_by(slug=category_slug).first_or_404()
        q = q.filter_by(category_id=active_category.id)
    q = q.order_by(MediaItem.created_at.desc())
    pagination = _paginate(q, page)
    return render_template(
        "media_list.html",
        kind="audio",
        title="Audio",
        pagination=pagination,
        items=pagination.items,
        categories=_categories(kind="audio"),
        active_category=active_category,
    )


@bp.route("/audio/<slug>")
def audio_detail(slug: str):
    item = MediaItem.query.filter_by(slug=slug, kind=MediaItem.KIND_AUDIO).first_or_404()
    if not item.is_published:
        abort(404)
    item.view_count = (item.view_count or 0) + 1
    db.session.commit()
    return render_template("media_detail.html", item=item)


@bp.route("/ads")
def ads_list():
    page = request.args.get("page", 1, type=int)
    category_slug = request.args.get("category")
    q = Ad.query.filter_by(status=Ad.STATUS_PUBLISHED)
    active_category = None
    if category_slug:
        active_category = Category.query.filter_by(slug=category_slug).first_or_404()
        q = q.filter_by(category_id=active_category.id)
    q = q.order_by(Ad.is_featured.desc(), Ad.created_at.desc())
    pagination = _paginate(q, page)
    return render_template(
        "ads_list.html",
        pagination=pagination,
        ads=pagination.items,
        categories=_categories(kind="ad"),
        active_category=active_category,
    )


@bp.route("/ads/<slug>")
def ad_detail(slug: str):
    ad = Ad.query.filter_by(slug=slug).first_or_404()
    if not ad.is_published:
        abort(404)
    ad.view_count = (ad.view_count or 0) + 1
    db.session.commit()
    return render_template("ad_detail.html", ad=ad)


@bp.route("/search")
def search():
    raw = (request.args.get("q") or "").strip()
    page = request.args.get("page", 1, type=int)
    results: dict = {"articles": [], "media": [], "ads": [], "q": raw}
    if raw:
        like = f"%{raw}%"
        results["articles"] = (
            Article.query.filter(
                Article.status == Article.STATUS_PUBLISHED,
                or_(
                    Article.title.ilike(like),
                    Article.summary.ilike(like),
                    Article.body.ilike(like),
                ),
            )
            .order_by(Article.created_at.desc())
            .limit(30)
            .all()
        )
        results["media"] = (
            MediaItem.query.filter(
                MediaItem.status == MediaItem.STATUS_PUBLISHED,
                or_(MediaItem.title.ilike(like), MediaItem.description.ilike(like)),
            )
            .order_by(MediaItem.created_at.desc())
            .limit(30)
            .all()
        )
        results["ads"] = (
            Ad.query.filter(
                Ad.status == Ad.STATUS_PUBLISHED,
                or_(Ad.title.ilike(like), Ad.description.ilike(like), Ad.location.ilike(like)),
            )
            .order_by(Ad.created_at.desc())
            .limit(30)
            .all()
        )
    return render_template("search.html", **results, page=page)


@bp.route("/about")
def about():
    return render_template("about.html")


@bp.get("/health")
def health():
    return "ok", 200


@bp.get("/api/info")
def api_info():
    return jsonify(
        name="AhantaPulse",
        region="Ahanta, Ghana",
        articles=Article.query.filter_by(status=Article.STATUS_PUBLISHED).count(),
        videos=MediaItem.query.filter_by(
            status=MediaItem.STATUS_PUBLISHED, kind=MediaItem.KIND_VIDEO
        ).count(),
        audio=MediaItem.query.filter_by(
            status=MediaItem.STATUS_PUBLISHED, kind=MediaItem.KIND_AUDIO
        ).count(),
        ads=Ad.query.filter_by(status=Ad.STATUS_PUBLISHED).count(),
    )


@bp.post("/api/notify")
def api_notify():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or request.form.get("email") or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@", 1)[-1]:
        return jsonify(error="Please enter a valid email address."), 400
    existing = NotifySignup.query.filter_by(email=email).first()
    if existing is None:
        db.session.add(NotifySignup(email=email))
        db.session.commit()
    return jsonify(ok=True, message="You're on the list. We'll let you know about updates.")
