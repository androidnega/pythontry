"""Admin (and writer) routes: dashboard + CRUD for content, categories, users.

Writers can manage their own content. Admins can manage everything plus users.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_

from extensions import db
from forms import (
    AdForm,
    ArticleForm,
    CategoryForm,
    DeleteForm,
    MediaForm,
    PortraitForm,
    SmtpSettingsForm,
    TestEmailForm,
    TinymceSettingsForm,
    UserAdminForm,
    UserCreateForm,
)
from models import (
    Ad,
    Article,
    Category,
    Comment,
    MediaItem,
    NotifySignup,
    Order,
    Portrait,
    PortraitImage,
    Tag,
    User,
)
from utils import (
    admin_required,
    ai_configured,
    ai_draft_article,
    ai_improve_article,
    ai_seo_meta,
    broadcast_new_article,
    can_edit,
    delete_original,
    delete_upload,
    get_app_setting,
    get_smtp_config,
    get_tinymce_key,
    make_watermarked_preview,
    parse_tags,
    render_markdown,
    save_original_image,
    save_upload,
    send_email,
    set_app_setting,
    slugify,
    smtp_ready,
    SMTP_KEYS,
    unique_slug,
)


def _sync_tags(article: Article, raw: str | None) -> None:
    """Replace `article.tags` with rows derived from a comma-separated string."""
    names = parse_tags(raw)
    new_tags: list[Tag] = []
    seen_slugs: set[str] = set()
    for name in names:
        slug = slugify(name, max_length=80)
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        tag = Tag.query.filter_by(slug=slug).first()
        if tag is None:
            tag = Tag(name=name, slug=slug)
            db.session.add(tag)
        elif tag.name != name and name:
            tag.name = name
        new_tags.append(tag)
    article.tags = new_tags

bp = Blueprint("admin", __name__)


def _ensure_can_edit(obj) -> None:
    if not can_edit(obj):
        abort(403)


def _category_choices(kind: str | None = None):
    q = Category.query
    if kind:
        q = q.filter(or_(Category.kind == kind, Category.kind == "all"))
    rows = q.order_by(Category.name).all()
    return [(0, "(no category)")] + [(c.id, f"{c.name}") for c in rows]


def _coerce_category(form_value: int | None) -> int | None:
    return form_value if form_value and form_value > 0 else None


@bp.before_request
@login_required
def _require_login():
    return None


@bp.route("/")
def dashboard():
    is_admin = current_user.is_admin

    def _scope(model):
        q = model.query
        return q if is_admin else q.filter_by(author_id=current_user.id)

    counts = {
        "articles": _scope(Article).count(),
        "videos": _scope(MediaItem).filter_by(kind=MediaItem.KIND_VIDEO).count(),
        "ads": _scope(Ad).count(),
    }
    if is_admin:
        # Portraits are monetised so writers never see them in their dashboard.
        counts["portraits"] = Portrait.query.count()
    recent_articles = (
        _scope(Article).order_by(Article.created_at.desc()).limit(5).all()
    )
    recent_media = (
        _scope(MediaItem).order_by(MediaItem.created_at.desc()).limit(5).all()
    )
    recent_ads = _scope(Ad).order_by(Ad.created_at.desc()).limit(5).all()
    return render_template(
        "admin/dashboard.html",
        counts=counts,
        recent_articles=recent_articles,
        recent_media=recent_media,
        recent_ads=recent_ads,
    )


# ---------------------------------------------------------------- Articles ---


@bp.route("/articles")
def articles():
    q = Article.query
    if not current_user.is_admin:
        q = q.filter_by(author_id=current_user.id)
    rows = q.order_by(Article.created_at.desc()).all()
    return render_template("admin/articles_list.html", articles=rows, delete_form=DeleteForm())


@bp.route("/articles/new", methods=["GET", "POST"])
@bp.route("/articles/<int:article_id>/edit", methods=["GET", "POST"])
def article_edit(article_id: int | None = None):
    article = db.session.get(Article, article_id) if article_id else None
    if article:
        _ensure_can_edit(article)

    form = ArticleForm(obj=article if article else None)
    form.category_id.choices = _category_choices(kind="news")
    if request.method == "GET" and article:
        if article.category_id:
            form.category_id.data = article.category_id
        if article.tags:
            form.tags.data = ", ".join(t.name for t in article.tags)
        # Older articles are stored as Markdown; Quill needs HTML to render
        # them. Convert here on display only — the post-back will be HTML
        # from the editor itself, so the body migrates to HTML on first save.
        if article.body:
            form.body.data = render_markdown(article.body)

    if form.validate_on_submit():
        if article is None:
            article = Article(author_id=current_user.id, body="")
            db.session.add(article)

        article.title = form.title.data.strip()
        article.summary = (form.summary.data or "").strip() or None
        article.body = form.body.data or ""
        article.category_id = _coerce_category(form.category_id.data)
        article.is_featured = bool(form.is_featured.data)
        new_status = form.status.data
        just_published = (
            article.status != Article.STATUS_PUBLISHED
            and new_status == Article.STATUS_PUBLISHED
        )
        if just_published:
            article.published_at = datetime.now(timezone.utc)
        article.status = new_status

        if not article.slug:
            base = slugify(article.title)
            with db.session.no_autoflush:
                article.slug = unique_slug(
                    base, lambda s: Article.query.filter_by(slug=s).first()
                )

        _sync_tags(article, form.tags.data)

        if form.remove_cover.data and article.cover_image:
            delete_upload(article.cover_image)
            article.cover_image = None
        if form.cover.data and form.cover.data.filename:
            try:
                rel = save_upload(
                    form.cover.data,
                    subdir="articles",
                    allowed=current_app.config["ALLOWED_IMAGE_EXT"],
                )
            except ValueError as exc:
                form.cover.errors.append(str(exc))
                return render_template(
                    "admin/article_form.html",
                    form=form, article=article,
                    ai_ready=ai_configured(),
                    ai_model=current_app.config.get("AI_MODEL", ""),
                )
            delete_upload(article.cover_image)
            article.cover_image = rel

        db.session.commit()

        # Fire-and-forget email broadcast on first publish (skips silently if
        # SMTP isn't configured or there are no subscribers).
        if just_published and smtp_ready():
            try:
                broadcast_new_article(current_app._get_current_object(), article.id)
                flash("Article saved and subscriber broadcast queued.", "success")
            except Exception:  # noqa: BLE001
                flash("Article saved (broadcast failed to start).", "warning")
            else:
                return redirect(url_for("admin.articles"))
        else:
            flash("Article saved.", "success")
        return redirect(url_for("admin.articles"))

    return render_template(
        "admin/article_form.html",
        form=form, article=article,
        ai_ready=ai_configured(),
        ai_model=current_app.config.get("AI_MODEL", ""),
    )


@bp.post("/articles/<int:article_id>/delete")
def article_delete(article_id: int):
    article = db.session.get(Article, article_id) or abort(404)
    _ensure_can_edit(article)
    form = DeleteForm()
    if form.validate_on_submit():
        delete_upload(article.cover_image)
        db.session.delete(article)
        db.session.commit()
        flash("Article deleted.", "success")
    return redirect(url_for("admin.articles"))


# ------------------------------------------------------------------ Media ---


@bp.route("/media")
def media_list():
    q = MediaItem.query
    if not current_user.is_admin:
        q = q.filter_by(author_id=current_user.id)
    rows = q.order_by(MediaItem.created_at.desc()).all()
    return render_template("admin/media_list.html", items=rows, delete_form=DeleteForm())


@bp.route("/media/new", methods=["GET", "POST"])
@bp.route("/media/<int:media_id>/edit", methods=["GET", "POST"])
def media_edit(media_id: int | None = None):
    item = db.session.get(MediaItem, media_id) if media_id else None
    if item:
        _ensure_can_edit(item)

    form = MediaForm(obj=item if item else None)
    form.category_id.choices = _category_choices()
    if request.method == "GET" and item and item.category_id:
        form.category_id.data = item.category_id
    form._existing_file_path = item.file_path if item else None

    if form.validate_on_submit():
        if item is None:
            item = MediaItem(author_id=current_user.id, kind=form.kind.data)
            db.session.add(item)

        item.title = form.title.data.strip()
        item.description = (form.description.data or "").strip() or None
        item.kind = form.kind.data
        item.source_type = form.source_type.data
        item.category_id = _coerce_category(form.category_id.data)
        item.is_featured = bool(form.is_featured.data)
        item.status = form.status.data

        if not item.slug:
            base = slugify(item.title)
            with db.session.no_autoflush:
                item.slug = unique_slug(
                    base, lambda s: MediaItem.query.filter_by(slug=s).first()
                )

        if item.source_type == MediaItem.SOURCE_EMBED:
            item.embed_url = (form.embed_url.data or "").strip()
            if item.file_path:
                delete_upload(item.file_path)
                item.file_path = None
        else:
            item.embed_url = None
            if form.media_file.data and form.media_file.data.filename:
                allowed = (
                    current_app.config["ALLOWED_VIDEO_EXT"]
                    if item.kind == MediaItem.KIND_VIDEO
                    else current_app.config["ALLOWED_AUDIO_EXT"]
                )
                try:
                    rel = save_upload(
                        form.media_file.data,
                        subdir=f"{item.kind}s",
                        allowed=allowed,
                    )
                except ValueError as exc:
                    form.media_file.errors.append(str(exc))
                    return render_template("admin/media_form.html", form=form, item=item)
                if item.file_path:
                    delete_upload(item.file_path)
                item.file_path = rel

        if form.remove_thumbnail.data and item.thumbnail_path:
            delete_upload(item.thumbnail_path)
            item.thumbnail_path = None
        if form.thumbnail.data and form.thumbnail.data.filename:
            try:
                rel = save_upload(
                    form.thumbnail.data,
                    subdir="thumbnails",
                    allowed=current_app.config["ALLOWED_IMAGE_EXT"],
                )
            except ValueError as exc:
                form.thumbnail.errors.append(str(exc))
                return render_template("admin/media_form.html", form=form, item=item)
            delete_upload(item.thumbnail_path)
            item.thumbnail_path = rel

        db.session.commit()
        flash("Media saved.", "success")
        return redirect(url_for("admin.media_list"))

    return render_template("admin/media_form.html", form=form, item=item)


@bp.post("/media/<int:media_id>/delete")
def media_delete(media_id: int):
    item = db.session.get(MediaItem, media_id) or abort(404)
    _ensure_can_edit(item)
    form = DeleteForm()
    if form.validate_on_submit():
        delete_upload(item.file_path)
        delete_upload(item.thumbnail_path)
        db.session.delete(item)
        db.session.commit()
        flash("Media deleted.", "success")
    return redirect(url_for("admin.media_list"))


# -------------------------------------------------------------------- Ads ---


@bp.route("/ads")
def ads_list():
    q = Ad.query
    if not current_user.is_admin:
        q = q.filter_by(author_id=current_user.id)
    rows = q.order_by(Ad.created_at.desc()).all()
    return render_template("admin/ads_list.html", ads=rows, delete_form=DeleteForm())


@bp.route("/ads/new", methods=["GET", "POST"])
@bp.route("/ads/<int:ad_id>/edit", methods=["GET", "POST"])
def ad_edit(ad_id: int | None = None):
    ad = db.session.get(Ad, ad_id) if ad_id else None
    if ad:
        _ensure_can_edit(ad)

    form = AdForm(obj=ad if ad else None)
    form.category_id.choices = _category_choices(kind="ad")
    if request.method == "GET" and ad and ad.category_id:
        form.category_id.data = ad.category_id

    if form.validate_on_submit():
        if ad is None:
            ad = Ad(author_id=current_user.id)
            db.session.add(ad)

        ad.title = form.title.data.strip()
        ad.description = (form.description.data or "").strip() or None
        ad.price = (form.price.data or "").strip() or None
        ad.currency = (form.currency.data or "GHS").strip() or "GHS"
        ad.contact_phone = (form.contact_phone.data or "").strip() or None
        ad.contact_whatsapp = (form.contact_whatsapp.data or "").strip() or None
        ad.contact_email = (form.contact_email.data or "").strip() or None
        ad.location = (form.location.data or "").strip() or None
        ad.external_url = (form.external_url.data or "").strip() or None
        ad.category_id = _coerce_category(form.category_id.data)
        ad.is_featured = bool(form.is_featured.data)
        ad.status = form.status.data

        if not ad.slug:
            base = slugify(ad.title)
            with db.session.no_autoflush:
                ad.slug = unique_slug(
                    base, lambda s: Ad.query.filter_by(slug=s).first()
                )

        if form.remove_image.data and ad.image_path:
            delete_upload(ad.image_path)
            ad.image_path = None
        if form.image.data and form.image.data.filename:
            try:
                rel = save_upload(
                    form.image.data,
                    subdir="ads",
                    allowed=current_app.config["ALLOWED_IMAGE_EXT"],
                )
            except ValueError as exc:
                form.image.errors.append(str(exc))
                return render_template("admin/ad_form.html", form=form, ad=ad)
            delete_upload(ad.image_path)
            ad.image_path = rel

        db.session.commit()
        flash("Ad saved.", "success")
        return redirect(url_for("admin.ads_list"))

    return render_template("admin/ad_form.html", form=form, ad=ad)


@bp.post("/ads/<int:ad_id>/delete")
def ad_delete(ad_id: int):
    ad = db.session.get(Ad, ad_id) or abort(404)
    _ensure_can_edit(ad)
    form = DeleteForm()
    if form.validate_on_submit():
        delete_upload(ad.image_path)
        db.session.delete(ad)
        db.session.commit()
        flash("Ad deleted.", "success")
    return redirect(url_for("admin.ads_list"))


# ------------------------------------------------------------ Portraits ---


@bp.route("/portraits")
@admin_required
def portraits_list():
    q = Portrait.query
    if not current_user.is_admin:
        q = q.filter_by(author_id=current_user.id)
    rows = q.order_by(Portrait.created_at.desc()).all()
    return render_template(
        "admin/portraits_list.html", portraits=rows, delete_form=DeleteForm()
    )


@bp.route("/portraits/new", methods=["GET", "POST"])
@bp.route("/portraits/<int:portrait_id>/edit", methods=["GET", "POST"])
@admin_required
def portrait_edit(portrait_id: int | None = None):
    portrait = db.session.get(Portrait, portrait_id) if portrait_id else None
    if portrait:
        _ensure_can_edit(portrait)

    form = PortraitForm(obj=portrait if portrait else None)
    if request.method == "GET" and portrait and portrait.price_pesewas:
        from decimal import Decimal

        form.price.data = Decimal(portrait.price_pesewas) / Decimal(100)

    if form.validate_on_submit():
        is_new = portrait is None
        if is_new:
            portrait = Portrait(author_id=current_user.id)
            db.session.add(portrait)

        portrait.title = form.title.data.strip()
        portrait.description = (form.description.data or "").strip() or None
        portrait.price_pesewas = int((form.price.data or 0) * 100)
        portrait.currency = current_app.config.get("PAYSTACK_CURRENCY", "GHS")
        portrait.is_featured = bool(form.is_featured.data)
        portrait.status = form.status.data
        portrait.card_aspect = (form.card_aspect.data or "natural").strip().lower()
        try:
            fx = int(form.focal_x.data) if form.focal_x.data is not None else 50
            fy = int(form.focal_y.data) if form.focal_y.data is not None else 50
        except (TypeError, ValueError):
            fx, fy = 50, 50
        portrait.focal_x = max(0, min(100, fx))
        portrait.focal_y = max(0, min(100, fy))

        if not portrait.slug:
            base = slugify(portrait.title)
            with db.session.no_autoflush:
                portrait.slug = unique_slug(
                    base, lambda s: Portrait.query.filter_by(slug=s).first()
                )

        if form.image.data and form.image.data.filename:
            try:
                rel_original, original_filename, width, height = save_original_image(
                    form.image.data, subdir="portraits"
                )
            except ValueError as exc:
                form.image.errors.append(str(exc))
                return render_template("admin/portrait_form.html", form=form, portrait=portrait)
            originals_root = str(current_app.config["ORIGINALS_DIR"])
            src_abs = os.path.join(originals_root, rel_original)
            try:
                preview_rel = make_watermarked_preview(
                    src_abs,
                    subdir="portraits",
                    max_width=current_app.config["PORTRAIT_PREVIEW_MAX_WIDTH"],
                    watermark_text=current_app.config["WATERMARK_TEXT"],
                )
            except Exception as exc:
                # If preview gen fails we still keep the original around.
                form.image.errors.append(f"Could not generate preview: {exc}")
                delete_original(rel_original)
                return render_template("admin/portrait_form.html", form=form, portrait=portrait)

            # Swap files, deleting the old ones
            delete_original(portrait.original_path)
            delete_upload(portrait.preview_path)
            portrait.original_path = rel_original
            portrait.original_filename = original_filename
            portrait.preview_path = preview_rel
            portrait.width = width
            portrait.height = height
            try:
                portrait.file_size_bytes = os.path.getsize(src_abs)
            except OSError:
                portrait.file_size_bytes = None
        elif is_new:
            form.image.errors.append("Please upload the high-resolution image.")
            db.session.rollback()
            return render_template("admin/portrait_form.html", form=form, portrait=None)

        # Make sure the portrait has an ID before attaching extras
        db.session.flush()

        # Handle additional uploads (alternate views)
        extras_files = [f for f in (form.extra_images.data or []) if f and getattr(f, "filename", "")]
        max_extras = 5
        existing_extras = len(portrait.extra_images or [])
        slots_left = max(0, max_extras - existing_extras)
        if len(extras_files) > slots_left:
            extras_files = extras_files[:slots_left]
            flash(
                f"Only {slots_left} more view(s) can be added (max {max_extras}).",
                "warning",
            )

        originals_root = str(current_app.config["ORIGINALS_DIR"])
        for f in extras_files:
            try:
                rel_original, original_filename, width, height = save_original_image(
                    f, subdir="portraits"
                )
            except ValueError as exc:
                flash(f"Skipped “{f.filename}”: {exc}", "warning")
                continue
            src_abs = os.path.join(originals_root, rel_original)
            try:
                preview_rel = make_watermarked_preview(
                    src_abs,
                    subdir="portraits",
                    max_width=current_app.config["PORTRAIT_PREVIEW_MAX_WIDTH"],
                    watermark_text=current_app.config["WATERMARK_TEXT"],
                )
            except Exception as exc:
                delete_original(rel_original)
                flash(f"Skipped “{f.filename}”: preview generation failed ({exc}).", "warning")
                continue
            try:
                size = os.path.getsize(src_abs)
            except OSError:
                size = None
            extra = PortraitImage(
                portrait_id=portrait.id,
                preview_path=preview_rel,
                original_path=rel_original,
                original_filename=original_filename,
                width=width,
                height=height,
                file_size_bytes=size,
                position=(portrait.extra_images[-1].position + 1) if portrait.extra_images else 1,
            )
            db.session.add(extra)

        db.session.commit()
        flash("Portrait saved.", "success")
        return redirect(url_for("admin.portrait_edit", portrait_id=portrait.id))

    return render_template("admin/portrait_form.html", form=form, portrait=portrait)


@bp.post("/portraits/<int:portrait_id>/delete")
@admin_required
def portrait_delete(portrait_id: int):
    portrait = db.session.get(Portrait, portrait_id) or abort(404)
    _ensure_can_edit(portrait)
    form = DeleteForm()
    if form.validate_on_submit():
        for extra in list(portrait.extra_images or []):
            delete_upload(extra.preview_path)
            delete_original(extra.original_path)
        delete_upload(portrait.preview_path)
        delete_original(portrait.original_path)
        db.session.delete(portrait)
        db.session.commit()
        flash("Portrait deleted.", "success")
    return redirect(url_for("admin.portraits_list"))


@bp.post("/portraits/<int:portrait_id>/images/<int:image_id>/delete")
@admin_required
def portrait_image_delete(portrait_id: int, image_id: int):
    portrait = db.session.get(Portrait, portrait_id) or abort(404)
    _ensure_can_edit(portrait)
    extra = db.session.get(PortraitImage, image_id) or abort(404)
    if extra.portrait_id != portrait.id:
        abort(404)
    form = DeleteForm()
    if form.validate_on_submit():
        delete_upload(extra.preview_path)
        delete_original(extra.original_path)
        db.session.delete(extra)
        db.session.commit()
        flash("View removed.", "success")
    return redirect(url_for("admin.portrait_edit", portrait_id=portrait.id))


@bp.route("/orders")
@admin_required
def orders_list():
    rows = Order.query.order_by(Order.created_at.desc()).limit(200).all()
    return render_template("admin/orders_list.html", orders=rows)


# ----------------------------------------------------- Categories (admin) ---


@bp.route("/categories")
@admin_required
def categories():
    rows = Category.query.order_by(Category.kind, Category.name).all()
    return render_template(
        "admin/categories_list.html", categories=rows, delete_form=DeleteForm()
    )


@bp.route("/categories/new", methods=["GET", "POST"])
@bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@admin_required
def category_edit(category_id: int | None = None):
    category = db.session.get(Category, category_id) if category_id else None
    form = CategoryForm(obj=category if category else None)
    if form.validate_on_submit():
        if category is None:
            category = Category()
            db.session.add(category)
        category.name = form.name.data.strip()
        category.kind = form.kind.data
        category.description = (form.description.data or "").strip() or None
        if not category.slug:
            base = slugify(category.name)
            category.slug = unique_slug(
                base, lambda s: Category.query.filter_by(slug=s).first()
            )
        db.session.commit()
        flash("Category saved.", "success")
        return redirect(url_for("admin.categories"))
    return render_template("admin/category_form.html", form=form, category=category)


@bp.post("/categories/<int:category_id>/delete")
@admin_required
def category_delete(category_id: int):
    category = db.session.get(Category, category_id) or abort(404)
    form = DeleteForm()
    if form.validate_on_submit():
        db.session.delete(category)
        db.session.commit()
        flash("Category deleted.", "success")
    return redirect(url_for("admin.categories"))


# ---------------------------------------------------------- Users (admin) ---


@bp.route("/users")
@admin_required
def users():
    rows = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users_list.html", users=rows, delete_form=DeleteForm())


@bp.route("/users/new", methods=["GET", "POST"])
@admin_required
def user_new():
    form = UserCreateForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        email = form.email.data.strip().lower()
        if User.query.filter_by(username=username).first():
            form.username.errors.append("That username is already taken.")
        elif User.query.filter_by(email=email).first():
            form.email.errors.append("That email is already registered.")
        else:
            user = User(
                username=username,
                email=email,
                role=form.role.data,
                display_name=(form.display_name.data or "").strip() or None,
                is_active_flag=bool(form.is_active.data),
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash(f"User {user.username!r} created.", "success")
            return redirect(url_for("admin.users"))
    return render_template("admin/user_new.html", form=form)


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def user_edit(user_id: int):
    user = db.session.get(User, user_id) or abort(404)
    form = UserAdminForm(obj=user)
    if request.method == "GET":
        form.is_active.data = bool(user.is_active_flag)
    if form.validate_on_submit():
        user.display_name = (form.display_name.data or "").strip() or None
        user.email = form.email.data.strip().lower()
        user.role = form.role.data
        user.is_active_flag = bool(form.is_active.data)
        db.session.commit()
        flash("User updated.", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, user=user)


@bp.post("/users/<int:user_id>/delete")
@admin_required
def user_delete(user_id: int):
    user = db.session.get(User, user_id) or abort(404)
    if user.id == current_user.id:
        flash("You can't delete your own account while logged in.", "error")
        return redirect(url_for("admin.users"))
    form = DeleteForm()
    if form.validate_on_submit():
        db.session.delete(user)
        db.session.commit()
        flash("User deleted.", "success")
    return redirect(url_for("admin.users"))


# ──────────────────────────── Comments (admin) ────────────────────────────


@bp.route("/comments")
@admin_required
def comments_list():
    """Recent comments with quick approve/hide/delete controls."""
    show = request.args.get("show", "all")  # all | hidden | approved
    page = request.args.get("page", 1, type=int)
    q = Comment.query
    if show == "hidden":
        q = q.filter(Comment.is_approved.is_(False))
    elif show == "approved":
        q = q.filter(Comment.is_approved.is_(True))
    q = q.order_by(Comment.created_at.desc())
    pagination = q.paginate(page=max(page, 1), per_page=25, error_out=False)
    counts = {
        "all":      Comment.query.count(),
        "approved": Comment.query.filter_by(is_approved=True).count(),
        "hidden":   Comment.query.filter_by(is_approved=False).count(),
    }
    return render_template(
        "admin/comments_list.html",
        pagination=pagination,
        comments=pagination.items,
        show=show,
        counts=counts,
        delete_form=DeleteForm(),
    )


@bp.post("/comments/<int:comment_id>/toggle")
@admin_required
def comment_toggle(comment_id: int):
    c = db.session.get(Comment, comment_id) or abort(404)
    c.is_approved = not c.is_approved
    db.session.commit()
    flash(f"Comment {'approved' if c.is_approved else 'hidden'}.", "success")
    return redirect(request.referrer or url_for("admin.comments_list"))


@bp.post("/comments/<int:comment_id>/delete")
@admin_required
def comment_delete(comment_id: int):
    c = db.session.get(Comment, comment_id) or abort(404)
    form = DeleteForm()
    if form.validate_on_submit():
        db.session.delete(c)
        db.session.commit()
        flash("Comment deleted.", "success")
    return redirect(request.referrer or url_for("admin.comments_list"))


# ──────────────────────────── Settings (admin) ────────────────────────────


@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    """Email/SMTP settings, plus a quick test-email tool."""
    cfg = get_smtp_config()
    form = SmtpSettingsForm(
        enabled=cfg["enabled"],
        host=cfg["host"],
        port=cfg["port"] or 587,
        username=cfg["username"],
        use_tls=cfg["use_tls"] if any(cfg.values()) else True,
        use_ssl=cfg["use_ssl"],
        from_email=cfg["from_email"],
        from_name=cfg["from_name"],
    )
    test_form = TestEmailForm()
    tinymce_form = TinymceSettingsForm(api_key=get_app_setting("tinymce_api_key") or "")

    # TinyMCE editor key — handle first so its POST isn't swallowed by the
    # SMTP form (whose fields are all Optional and would otherwise validate).
    if "submit_tinymce" in request.form and tinymce_form.validate_on_submit():
        set_app_setting("tinymce_api_key", (tinymce_form.api_key.data or "").strip())
        flash("Editor key saved. Reload the article form to see it apply.", "success")
        return redirect(url_for("admin.settings"))

    if form.submit.data and "submit_tinymce" not in request.form and form.validate_on_submit():
        set_app_setting("smtp_enabled",   "1" if form.enabled.data else "0")
        set_app_setting("smtp_host",      (form.host.data or "").strip())
        set_app_setting("smtp_port",      str(form.port.data or 0))
        set_app_setting("smtp_username",  (form.username.data or "").strip())
        # Only overwrite the stored password when the admin types a new one.
        if form.password.data:
            set_app_setting("smtp_password", form.password.data)
        set_app_setting("smtp_use_tls",   "1" if form.use_tls.data else "0")
        set_app_setting("smtp_use_ssl",   "1" if form.use_ssl.data else "0")
        set_app_setting("smtp_from_email",(form.from_email.data or "").strip())
        set_app_setting("smtp_from_name", (form.from_name.data or "").strip())
        flash("SMTP settings saved.", "success")
        return redirect(url_for("admin.settings"))

    if test_form.submit.data and test_form.validate_on_submit():
        ok, err = send_email(
            test_form.to_addr.data.strip(),
            f"Test email from {current_app.config.get('SITE_NAME','site')}",
            "<p>If you can read this, your SMTP configuration works.</p>",
        )
        if ok:
            flash("Test email sent successfully.", "success")
        else:
            flash(f"Test email failed: {err}", "error")
        return redirect(url_for("admin.settings"))

    subscriber_count = NotifySignup.query.filter(NotifySignup.unsubscribed_at.is_(None)).count()
    user_count = User.query.count()
    return render_template(
        "admin/settings.html",
        form=form,
        test_form=test_form,
        tinymce_form=tinymce_form,
        tinymce_key_set=bool((tinymce_form.api_key.data or "").strip()),
        smtp_cfg=cfg,
        subscriber_count=subscriber_count,
        user_count=user_count,
    )


# ──────────────────────────── Subscribers (admin) ─────────────────────────


@bp.route("/subscribers")
@admin_required
def subscribers():
    page = request.args.get("page", 1, type=int)
    show = request.args.get("show", "active")
    q = NotifySignup.query
    if show == "active":
        q = q.filter(NotifySignup.unsubscribed_at.is_(None))
    elif show == "unsubscribed":
        q = q.filter(NotifySignup.unsubscribed_at.isnot(None))
    pagination = q.order_by(NotifySignup.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    counts = {
        "active": NotifySignup.query.filter(NotifySignup.unsubscribed_at.is_(None)).count(),
        "unsubscribed": NotifySignup.query.filter(NotifySignup.unsubscribed_at.isnot(None)).count(),
    }
    return render_template(
        "admin/subscribers.html",
        pagination=pagination,
        subscribers=pagination.items,
        delete_form=DeleteForm(),
        show=show,
        counts=counts,
    )


@bp.post("/subscribers/<int:sub_id>/delete")
@admin_required
def subscriber_delete(sub_id: int):
    sub = db.session.get(NotifySignup, sub_id) or abort(404)
    form = DeleteForm()
    if form.validate_on_submit():
        db.session.delete(sub)
        db.session.commit()
        flash("Subscriber removed.", "success")
    return redirect(url_for("admin.subscribers"))


@bp.get("/subscribers.csv")
@admin_required
def subscribers_csv():
    import csv, io
    rows = NotifySignup.query.order_by(NotifySignup.created_at.desc()).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "status", "subscribed_at", "unsubscribed_at"])
    for r in rows:
        w.writerow([
            r.email,
            "unsubscribed" if r.unsubscribed_at else "active",
            (r.created_at.isoformat() if r.created_at else ""),
            (r.unsubscribed_at.isoformat() if r.unsubscribed_at else ""),
        ])
    from flask import Response
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="subscribers.csv"'},
    )


# ───────────────────────── Editor APIs (JSON) ─────────────────────────

@bp.post("/api/upload-image")
def api_upload_image():
    """Save an image uploaded from the WYSIWYG editor and return its public URL."""
    f = request.files.get("file") or request.files.get("image")
    if not f or not f.filename:
        return jsonify(ok=False, error="No file provided."), 400
    try:
        rel = save_upload(f, subdir="article_images", allowed=current_app.config["ALLOWED_IMAGE_EXT"])
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    if rel is None:
        return jsonify(ok=False, error="Could not save the file."), 400
    return jsonify(ok=True, url=url_for("static", filename=rel))


def _json_or_400(field: str):
    data = request.get_json(silent=True) or {}
    value = (data.get(field) or "").strip()
    if not value:
        return None, (jsonify(ok=False, error=f"Missing field: {field}"), 400)
    return (data, value), None


@bp.post("/api/ai/draft")
def api_ai_draft():
    if not ai_configured():
        return jsonify(ok=False, error="AI is not configured on the server. Add AI_API_KEY (or OPENAI_API_KEY) and restart."), 503
    parsed, err = _json_or_400("brief")
    if err:
        return err
    _, brief = parsed
    try:
        html = ai_draft_article(brief)
    except Exception as exc:
        current_app.logger.exception("AI draft failed: %s", exc)
        return jsonify(ok=False, error=str(exc)), 502
    return jsonify(ok=True, html=html)


@bp.post("/api/ai/improve")
def api_ai_improve():
    if not ai_configured():
        return jsonify(ok=False, error="AI is not configured on the server. Add AI_API_KEY (or OPENAI_API_KEY) and restart."), 503
    parsed, err = _json_or_400("body")
    if err:
        return err
    data, body = parsed
    focus = (data.get("focus_keyword") or "").strip() or None
    try:
        html = ai_improve_article(body, focus_keyword=focus)
    except Exception as exc:
        current_app.logger.exception("AI improve failed: %s", exc)
        return jsonify(ok=False, error=str(exc)), 502
    return jsonify(ok=True, html=html)


@bp.post("/api/ai/seo")
def api_ai_seo():
    if not ai_configured():
        return jsonify(ok=False, error="AI is not configured on the server. Add AI_API_KEY (or OPENAI_API_KEY) and restart."), 503
    parsed, err = _json_or_400("body")
    if err:
        return err
    _, body = parsed
    try:
        result = ai_seo_meta(body)
    except Exception as exc:
        current_app.logger.exception("AI SEO failed: %s", exc)
        return jsonify(ok=False, error=str(exc)), 502
    return jsonify(ok=True, **result)
