"""Authentication routes: register, login, logout, profile, password change."""

from __future__ import annotations

from urllib.parse import urlparse

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
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_

from extensions import db
from forms import LoginForm, PasswordChangeForm, ProfileForm, RegisterForm
from models import User
from utils import delete_upload, save_upload

bp = Blueprint("auth", __name__)


def _safe_next(target: str | None) -> str | None:
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.netloc or parsed.scheme:
        return None
    if not target.startswith("/"):
        return None
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("public.home"))
    form = LoginForm()
    if form.validate_on_submit():
        ident = form.identifier.data.strip()
        user = User.query.filter(
            or_(User.username == ident, User.email == ident.lower())
        ).first()
        if user is None or not user.check_password(form.password.data):
            flash("Invalid username/email or password.", "error")
        elif not user.is_active:
            flash("This account is disabled.", "error")
        else:
            login_user(user, remember=bool(form.remember.data))
            flash(f"Welcome back, {user.name}.", "success")
            return redirect(_safe_next(request.args.get("next")) or url_for("public.home"))
    return render_template("auth/login.html", form=form)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if not current_app.config["ALLOW_REGISTRATION"]:
        abort(404)
    if current_user.is_authenticated:
        return redirect(url_for("public.home"))
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        email = form.email.data.strip().lower()
        if User.query.filter_by(username=username).first():
            form.username.errors.append("That username is taken.")
        elif User.query.filter_by(email=email).first():
            form.email.errors.append("That email is already registered.")
        else:
            user = User(
                username=username,
                email=email,
                role=User.ROLE_WRITER,
                display_name=(form.display_name.data or "").strip() or None,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account created. Welcome aboard!", "success")
            return redirect(url_for("admin.dashboard"))
    return render_template("auth/register.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("Signed out.", "info")
    return redirect(url_for("public.home"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.display_name = (form.display_name.data or "").strip() or None
        current_user.bio = (form.bio.data or "").strip() or None
        if form.avatar.data and form.avatar.data.filename:
            try:
                rel = save_upload(
                    form.avatar.data,
                    subdir="avatars",
                    allowed=current_app.config["ALLOWED_IMAGE_EXT"],
                )
            except ValueError as exc:
                form.avatar.errors.append(str(exc))
                return render_template("auth/profile.html", form=form)
            delete_upload(current_user.avatar_path)
            current_user.avatar_path = rel
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("auth.profile"))
    return render_template("auth/profile.html", form=form)


@bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    form = PasswordChangeForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            form.current_password.errors.append("Current password is incorrect.")
        else:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("Password updated.", "success")
            return redirect(url_for("auth.profile"))
    return render_template("auth/password.html", form=form)
