"""Admin (and writer) routes: dashboard + CRUD for content, categories, users.

Writers can manage their own content. Admins can manage everything plus users.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
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
    UserAdminForm,
)
from models import Ad, Article, Category, MediaItem, User
from utils import (
    admin_required,
    can_edit,
    delete_upload,
    save_upload,
    slugify,
    unique_slug,
)

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
        "audio": _scope(MediaItem).filter_by(kind=MediaItem.KIND_AUDIO).count(),
        "ads": _scope(Ad).count(),
    }
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
    if request.method == "GET" and article and article.category_id:
        form.category_id.data = article.category_id

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
        if article.status != Article.STATUS_PUBLISHED and new_status == Article.STATUS_PUBLISHED:
            article.published_at = datetime.now(timezone.utc)
        article.status = new_status

        if not article.slug:
            base = slugify(article.title)
            article.slug = unique_slug(
                base, lambda s: Article.query.filter_by(slug=s).first()
            )

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
                return render_template("admin/article_form.html", form=form, article=article)
            delete_upload(article.cover_image)
            article.cover_image = rel

        db.session.commit()
        flash("Article saved.", "success")
        return redirect(url_for("admin.articles"))

    return render_template("admin/article_form.html", form=form, article=article)


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
            ad.slug = unique_slug(base, lambda s: Ad.query.filter_by(slug=s).first())

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
