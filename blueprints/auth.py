"""Authentication routes: register, login, logout, profile, password change,
plus Sign in with Google.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode, urlparse

import requests
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_

from extensions import db
from forms import LoginForm, PasswordChangeForm, ProfileForm, RegisterForm
from models import User
from utils import (
    delete_upload,
    get_google_oauth_config,
    google_oauth_enabled,
    save_upload,
    slugify,
    unique_slug,
)

bp = Blueprint("auth", __name__)

# Google's OpenID-Connect endpoints. Hard-coded to avoid an extra HTTPS
# round-trip to the discovery document on every login.
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"


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
        return redirect(url_for("admin.dashboard"))
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
            return redirect(_safe_next(request.args.get("next")) or url_for("admin.dashboard"))
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


# ─────────────────────────── Google OAuth ────────────────────────────


def _google_redirect_uri() -> str:
    """The redirect URI we register with Google's API console.

    Must EXACTLY match an entry under "Authorized redirect URIs" in the
    Google Cloud OAuth client settings, including scheme and trailing
    slash. We honour `PREFERRED_URL_SCHEME` so reverse proxies that hand
    us http internally still produce https URLs.
    """
    return url_for("auth.google_callback", _external=True)


def _username_from_email(email: str) -> str:
    """Pick a unique, slug-safe username from an email address."""
    local = (email.split("@", 1)[0] or "user").lower()
    base = slugify(local) or "user"
    return unique_slug(base, lambda s: User.query.filter_by(username=s).first())


@bp.route("/login/google")
def google_login():
    """Kick off Google's OAuth 2.0 / OIDC authorization-code flow."""
    if current_user.is_authenticated:
        return redirect(_safe_next(request.args.get("next")) or url_for("admin.dashboard"))

    cfg = get_google_oauth_config()
    if not (cfg["client_id"] and cfg["client_secret"]):
        flash(
            "Sign-in with Google isn't configured yet. "
            "An administrator can enable it under Dashboard → Settings.",
            "error",
        )
        return redirect(url_for("auth.login"))

    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    session["oauth_next"] = _safe_next(request.args.get("next")) or ""

    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
        "access_type": "online",
    }
    return redirect(f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}")


@bp.route("/login/google/callback")
def google_callback():
    """Handle Google's redirect: exchange the code, find-or-create user, log in."""
    cfg = get_google_oauth_config()
    if not (cfg["client_id"] and cfg["client_secret"]):
        abort(404)

    # 1. Verify state (CSRF defence).
    expected_state = session.pop("oauth_state", None)
    next_url = session.pop("oauth_next", "") or url_for("public.home")
    if not expected_state or request.args.get("state") != expected_state:
        flash("Sign-in was rejected (state mismatch). Please try again.", "error")
        return redirect(url_for("auth.login"))

    # 2. Surface Google-side errors verbatim.
    err = request.args.get("error")
    if err:
        desc = request.args.get("error_description") or err
        flash(f"Google sign-in failed: {desc}", "error")
        return redirect(url_for("auth.login"))

    code = request.args.get("code")
    if not code:
        flash("Google sign-in failed: no authorization code returned.", "error")
        return redirect(url_for("auth.login"))

    # 3. Exchange the code for tokens.
    try:
        token_resp = requests.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "redirect_uri": _google_redirect_uri(),
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        current_app.logger.warning("Google token exchange failed: %s", exc)
        flash("Could not reach Google to verify your sign-in. Please try again.", "error")
        return redirect(url_for("auth.login"))

    if not token_resp.ok:
        current_app.logger.warning("Google token exchange %s: %s", token_resp.status_code, token_resp.text[:300])
        flash("Google rejected the sign-in. Please try again.", "error")
        return redirect(url_for("auth.login"))

    access_token = (token_resp.json() or {}).get("access_token", "")
    if not access_token:
        flash("Google did not return an access token. Please try again.", "error")
        return redirect(url_for("auth.login"))

    # 4. Fetch the user's profile.
    try:
        info_resp = requests.get(
            GOOGLE_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        current_app.logger.warning("Google userinfo failed: %s", exc)
        flash("Signed-in to Google but couldn't read your profile. Please retry.", "error")
        return redirect(url_for("auth.login"))

    info = info_resp.json() if info_resp.ok else {}
    email = (info.get("email") or "").strip().lower()
    sub = (info.get("sub") or "").strip()
    name = (info.get("name") or "").strip()
    verified = bool(info.get("email_verified"))

    if not email or not sub:
        flash("Google didn't share your email — sign-in cannot continue.", "error")
        return redirect(url_for("auth.login"))
    if not verified:
        flash("Your Google email isn't verified yet, so we can't sign you in.", "error")
        return redirect(url_for("auth.login"))

    # 5. Find or create the local user.
    user = (
        User.query.filter_by(oauth_provider="google", oauth_sub=sub).first()
        or User.query.filter_by(email=email).first()
    )
    if user is None:
        user = User(
            username=_username_from_email(email),
            email=email,
            role=User.ROLE_WRITER,  # lowest privilege; admins can promote later
            display_name=name or None,
            oauth_provider="google",
            oauth_sub=sub,
        )
        # Even though OAuth users don't log in by password we still seed an
        # unguessable hash so legacy DBs (where password_hash is NOT NULL)
        # accept the insert. They can set a real password later via the
        # forgot/profile flow if we ever expose one.
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
        db.session.commit()
    else:
        # Existing local user signing in via Google for the first time —
        # link the account so subsequent logins are one-click.
        changed = False
        if not user.oauth_provider:
            user.oauth_provider, user.oauth_sub = "google", sub
            changed = True
        if name and not user.display_name:
            user.display_name = name
            changed = True
        if changed:
            db.session.commit()

    if not user.is_active:
        flash("This account is disabled.", "error")
        return redirect(url_for("auth.login"))

    login_user(user, remember=True)
    flash(f"Welcome, {user.name}.", "success")
    return redirect(_safe_next(next_url) or url_for("public.home"))


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
