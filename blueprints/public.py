"""Public-facing routes: homepage, news, videos, ads, portraits, search, about."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from sqlalchemy import or_

from extensions import csrf, db
from forms import CheckoutForm
from models import Ad, Article, Category, MediaItem, NotifySignup, Order, Portrait, Tag, article_tags
from utils import (
    detect_embed,
    new_download_token,
    new_payment_reference,
    paystack_configured,
    paystack_initialize,
    paystack_verify,
    reading_time_minutes,
    verify_paystack_signature,
)

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


@bp.app_template_filter("reading_time")
def _reading_time_filter(text):
    return reading_time_minutes(text)


@bp.app_template_filter("sum_of_chars")
def _sum_of_chars_filter(value):
    """Deterministic non-negative int from a string — handy for picking a
    stable color/index from a slug in templates."""
    if not value:
        return 0
    return sum(ord(c) for c in str(value))


def _popular_articles(limit: int = 5, exclude_id: int | None = None):
    q = Article.query.filter_by(status=Article.STATUS_PUBLISHED)
    if exclude_id:
        q = q.filter(Article.id != exclude_id)
    return (
        q.order_by(Article.view_count.desc(), Article.created_at.desc())
        .limit(limit)
        .all()
    )


def _article_sidebar_ctx(exclude_ids: list[int] | None = None) -> dict:
    """Build the data used by templates/_article_sidebar.html so we can
    plug the same sticky sidebar into article detail, the news index,
    category pages, and tag pages."""
    from sqlalchemy import func as _func

    excl = exclude_ids or []
    popular_q = Article.query.filter_by(status=Article.STATUS_PUBLISHED)
    if excl:
        popular_q = popular_q.filter(~Article.id.in_(excl))
    popular = (
        popular_q.order_by(Article.view_count.desc(), Article.created_at.desc())
        .limit(5)
        .all()
    )

    recent = _latest_articles(limit=5, exclude_ids=excl)

    cat_rows = (
        db.session.query(Category, _func.count(Article.id).label("n"))
        .outerjoin(
            Article,
            (Article.category_id == Category.id)
            & (Article.status == Article.STATUS_PUBLISHED),
        )
        .filter(Category.kind.in_([Category.KIND_NEWS, Category.KIND_ALL]))
        .group_by(Category.id)
        .order_by(_func.count(Article.id).desc(), Category.name.asc())
        .limit(8)
        .all()
    )
    sidebar_categories = [{"category": c, "count": int(n or 0)} for (c, n) in cat_rows]

    tag_rows = (
        db.session.query(Tag, _func.count(Article.id).label("n"))
        .join(article_tags, Tag.id == article_tags.c.tag_id)
        .join(Article, Article.id == article_tags.c.article_id)
        .filter(Article.status == Article.STATUS_PUBLISHED)
        .group_by(Tag.id)
        .order_by(_func.count(Article.id).desc(), Tag.name.asc())
        .limit(18)
        .all()
    )
    sidebar_tags = [{"tag": t, "count": int(n or 0)} for (t, n) in tag_rows]

    return {
        "popular": popular,
        "recent_articles": recent,
        "sidebar_categories": sidebar_categories,
        "sidebar_tags": sidebar_tags,
    }


@bp.route("/")
def home():
    # Hero slider always shows the 3 newest published articles — never more,
    # never the same one twice, regardless of the is_featured flag.
    featured = _latest_articles(limit=3)
    exclude = [a.id for a in featured]
    # 12 = first 4 fill the under-hero "story shortcuts" strip, the rest
    # fall into the main grid below.
    latest = _latest_articles(limit=12, exclude_ids=exclude)
    return render_template(
        "home.html",
        featured=featured,
        latest=latest,
        videos=_latest_media(kind=MediaItem.KIND_VIDEO, limit=4),
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
    popular_tags = (
        Tag.query.join(Tag.articles)
        .filter(Article.status == Article.STATUS_PUBLISHED)
        .group_by(Tag.id)
        .order_by(db.func.count(Article.id).desc())
        .limit(12)
        .all()
    )
    return render_template(
        "news_list.html",
        pagination=pagination,
        articles=pagination.items,
        categories=_categories(kind="news"),
        active_category=active_category,
        popular_tags=popular_tags,
        **_article_sidebar_ctx(),
    )


@bp.route("/news/<slug>")
def article_detail(slug: str):
    article = Article.query.filter_by(slug=slug).first_or_404()
    if not article.is_published:
        abort(404)
    article.view_count = (article.view_count or 0) + 1
    db.session.commit()
    related_q = Article.query.filter(
        Article.id != article.id,
        Article.status == Article.STATUS_PUBLISHED,
    )
    if article.category_id:
        related_q = related_q.filter(Article.category_id == article.category_id)
    related = related_q.order_by(Article.created_at.desc()).limit(3).all()

    more_by_author = (
        Article.query.filter(
            Article.id != article.id,
            Article.status == Article.STATUS_PUBLISHED,
            Article.author_id == article.author_id,
        )
        .order_by(Article.created_at.desc())
        .limit(4)
        .all()
    )
    sidebar_ctx = _article_sidebar_ctx(exclude_ids=[article.id])
    # The article-detail "Most read" card excludes the current piece, so
    # override what the generic helper produced for that one key.
    sidebar_ctx["popular"] = _popular_articles(limit=5, exclude_id=article.id)

    return render_template(
        "article_detail.html",
        article=article,
        related=related,
        more_by_author=more_by_author,
        **sidebar_ctx,
    )


@bp.route("/tag/<slug>")
def tag_detail(slug: str):
    tag = Tag.query.filter_by(slug=slug).first_or_404()
    page = request.args.get("page", 1, type=int)
    q = (
        Article.query.filter(Article.status == Article.STATUS_PUBLISHED)
        .filter(Article.tags.any(Tag.id == tag.id))
        .order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
    )
    pagination = _paginate(q, page)
    return render_template(
        "tag.html",
        tag=tag,
        pagination=pagination,
        articles=pagination.items,
        **_article_sidebar_ctx(),
    )


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


# -------------------------------------------------- Portraits + Paystack ---


@bp.route("/portraits")
def portraits_list():
    page = request.args.get("page", 1, type=int)
    q = Portrait.query.filter_by(status=Portrait.STATUS_PUBLISHED).order_by(
        Portrait.is_featured.desc(), Portrait.created_at.desc()
    )
    pagination = _paginate(q, page)
    return render_template(
        "portraits_list.html",
        pagination=pagination,
        portraits=pagination.items,
    )


@bp.route("/portraits/<slug>")
def portrait_detail(slug: str):
    portrait = Portrait.query.filter_by(slug=slug).first_or_404()
    if not portrait.is_published:
        abort(404)
    portrait.view_count = (portrait.view_count or 0) + 1
    db.session.commit()
    form = CheckoutForm()
    related = (
        Portrait.query.filter(
            Portrait.status == Portrait.STATUS_PUBLISHED,
            Portrait.id != portrait.id,
        )
        .order_by(Portrait.is_featured.desc(), Portrait.created_at.desc())
        .limit(4)
        .all()
    )
    return render_template(
        "portrait_detail.html",
        portrait=portrait,
        form=form,
        paystack_ready=paystack_configured(),
        related_portraits=related,
    )


@bp.post("/portraits/<slug>/buy")
def portrait_buy(slug: str):
    portrait = Portrait.query.filter_by(slug=slug).first_or_404()
    if not portrait.is_published:
        abort(404)
    if not paystack_configured():
        flash("Payments are not set up yet. Please contact us to buy this portrait.", "error")
        return redirect(url_for("public.portrait_detail", slug=slug))
    if (portrait.price_pesewas or 0) <= 0:
        flash("This portrait can't be purchased right now.", "error")
        return redirect(url_for("public.portrait_detail", slug=slug))

    form = CheckoutForm()
    if not form.validate_on_submit():
        return render_template(
            "portrait_detail.html",
            portrait=portrait,
            form=form,
            paystack_ready=True,
        )

    reference = new_payment_reference("AP")
    order = Order(
        portrait_id=portrait.id,
        buyer_email=form.buyer_email.data.strip().lower(),
        buyer_name=(form.buyer_name.data or "").strip() or None,
        amount_pesewas=int(portrait.price_pesewas),
        currency=portrait.currency or current_app.config.get("PAYSTACK_CURRENCY", "GHS"),
        paystack_reference=reference,
        download_limit=current_app.config["PORTRAIT_MAX_DOWNLOADS"],
    )
    db.session.add(order)
    db.session.commit()

    try:
        result = paystack_initialize(
            amount_pesewas=order.amount_pesewas,
            email=order.buyer_email,
            callback_url=url_for("public.portrait_callback", _external=True),
            reference=reference,
            currency=order.currency,
            metadata={
                "portrait_id": portrait.id,
                "portrait_title": portrait.title,
            },
        )
    except Exception as exc:  # network/API failure
        order.status = Order.STATUS_FAILED
        order.paystack_status = "init_failed"
        db.session.commit()
        current_app.logger.exception("Paystack init failed: %s", exc)
        flash("We couldn't start the payment. Please try again.", "error")
        return redirect(url_for("public.portrait_detail", slug=slug))

    data = result.get("data") or {}
    auth_url = data.get("authorization_url")
    if not auth_url:
        order.status = Order.STATUS_FAILED
        order.paystack_status = "no_auth_url"
        db.session.commit()
        flash("Payment provider didn't return a checkout URL. Please try again.", "error")
        return redirect(url_for("public.portrait_detail", slug=slug))

    return redirect(auth_url)


@bp.get("/portraits/checkout/callback")
@csrf.exempt
def portrait_callback():
    reference = (request.args.get("reference") or request.args.get("trxref") or "").strip()
    if not reference:
        abort(400)
    order = Order.query.filter_by(paystack_reference=reference).first()
    if order is None:
        abort(404)

    portrait = order.portrait
    if order.is_paid:
        return redirect(url_for("public.portrait_download_ready", token=order.download_token))

    try:
        result = paystack_verify(reference)
    except Exception as exc:
        current_app.logger.exception("Paystack verify failed: %s", exc)
        return render_template("portrait_failed.html", portrait=portrait, order=order)

    data = (result.get("data") or {})
    status = (data.get("status") or "").lower()
    order.paystack_status = status or "unknown"
    paid_pesewas = int(data.get("amount") or 0)

    if status == "success" and paid_pesewas >= order.amount_pesewas:
        _mark_order_paid(order)
        db.session.commit()
        return redirect(url_for("public.portrait_download_ready", token=order.download_token))

    if status == "abandoned":
        order.status = Order.STATUS_ABANDONED
    else:
        order.status = Order.STATUS_FAILED
    db.session.commit()
    return render_template("portrait_failed.html", portrait=portrait, order=order)


def _mark_order_paid(order: Order) -> None:
    """Idempotently mark an order as paid and issue a download token."""
    if order.is_paid:
        return
    order.status = Order.STATUS_PAID
    order.paid_at = datetime.now(timezone.utc)
    if not order.download_token:
        order.download_token = new_download_token()
    hours = current_app.config["PORTRAIT_DOWNLOAD_TTL_HOURS"]
    order.token_expires_at = order.paid_at + timedelta(hours=hours)
    if order.portrait:
        order.portrait.sales_count = (order.portrait.sales_count or 0) + 1


@bp.get("/portraits/download/<token>")
def portrait_download_ready(token: str):
    order = Order.query.filter_by(download_token=token).first_or_404()
    if not order.is_paid:
        abort(403)
    return render_template("portrait_download.html", order=order, portrait=order.portrait)


@bp.get("/portraits/download/<token>/file")
def portrait_download_file(token: str):
    order = Order.query.filter_by(download_token=token).first_or_404()
    if not order.is_paid:
        abort(403)
    now = datetime.now(timezone.utc)
    expires = order.token_expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires is not None and expires < now:
        abort(410)  # Gone
    if (order.download_count or 0) >= (order.download_limit or 5):
        abort(429)  # Too Many

    portrait = order.portrait
    if portrait is None:
        abort(404)

    originals_root = str(current_app.config["ORIGINALS_DIR"])
    originals = portrait.all_originals or []
    files_on_disk: list[tuple[str, str]] = []
    for item in originals:
        p = os.path.join(originals_root, item["path"])
        if os.path.isfile(p):
            files_on_disk.append((p, item["filename"]))

    if not files_on_disk:
        abort(404)

    order.download_count = (order.download_count or 0) + 1
    db.session.commit()

    if len(files_on_disk) == 1:
        abs_path, name = files_on_disk[0]
        return send_file(abs_path, as_attachment=True, download_name=name)

    # Multiple originals → stream a single ZIP
    import io
    import zipfile

    buf = io.BytesIO()
    seen_names: set[str] = set()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        for idx, (abs_path, name) in enumerate(files_on_disk, start=1):
            arcname = name or os.path.basename(abs_path)
            base, ext = os.path.splitext(arcname)
            unique = arcname
            n = 1
            while unique in seen_names:
                unique = f"{base}-{n}{ext}"
                n += 1
            seen_names.add(unique)
            zf.write(abs_path, arcname=unique)
    buf.seek(0)
    zip_name = f"{portrait.slug or 'portrait'}.zip"
    return send_file(
        buf,
        as_attachment=True,
        download_name=zip_name,
        mimetype="application/zip",
    )


@bp.post("/webhooks/paystack")
@csrf.exempt
def paystack_webhook():
    signature = request.headers.get("x-paystack-signature")
    body = request.get_data()
    if not verify_paystack_signature(body, signature):
        abort(400)

    import json as _json
    try:
        payload = _json.loads(body.decode("utf-8")) if body else {}
    except (ValueError, UnicodeDecodeError):
        payload = {}
    event = payload.get("event")
    data = payload.get("data") or {}
    reference = data.get("reference")
    if not reference:
        return jsonify(ok=True)

    order = Order.query.filter_by(paystack_reference=reference).first()
    if order is None:
        return jsonify(ok=True)

    status = (data.get("status") or "").lower()
    order.paystack_status = status or event or "unknown"
    if event == "charge.success" and status == "success":
        paid = int(data.get("amount") or 0)
        if paid >= order.amount_pesewas:
            _mark_order_paid(order)
    db.session.commit()
    return jsonify(ok=True)


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
@csrf.exempt
def api_notify():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or request.form.get("email") or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@", 1)[-1]:
        return jsonify(error="Please enter a valid email address."), 400
    import secrets as _secrets
    existing = NotifySignup.query.filter_by(email=email).first()
    if existing is None:
        db.session.add(NotifySignup(
            email=email,
            unsubscribe_token=_secrets.token_urlsafe(24),
        ))
        db.session.commit()
    else:
        # Re-activate someone who unsubscribed previously and ensure a token exists.
        changed = False
        if existing.unsubscribed_at is not None:
            existing.unsubscribed_at = None
            changed = True
        if not existing.unsubscribe_token:
            existing.unsubscribe_token = _secrets.token_urlsafe(24)
            changed = True
        if changed:
            db.session.commit()
    return jsonify(ok=True, message="You're on the list. We'll let you know about updates.")


@bp.route("/unsubscribe/<token>", methods=["GET", "POST"])
def unsubscribe(token: str):
    """Public, no-auth unsubscribe via opaque token from notification emails."""
    sub = NotifySignup.query.filter_by(unsubscribe_token=token).first()
    if not sub:
        return render_template("unsubscribe.html", sub=None, done=False), 404
    if request.method == "POST":
        from datetime import datetime as _dt, timezone as _tz
        sub.unsubscribed_at = _dt.now(_tz.utc)
        db.session.commit()
        return render_template("unsubscribe.html", sub=sub, done=True)
    return render_template("unsubscribe.html", sub=sub, done=False)
