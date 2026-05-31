"""WTForms forms used by auth and admin blueprints."""

from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField,
    DecimalField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    URL,
    DataRequired,
    Email,
    EqualTo,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

from config import Config


class LoginForm(FlaskForm):
    identifier = StringField(
        "Username or email", validators=[DataRequired(), Length(max=255)]
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(max=255)])
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")


class RegisterForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=3, max=64)]
    )
    email = StringField(
        "Email", validators=[DataRequired(), Email(), Length(max=255)]
    )
    display_name = StringField("Display name", validators=[Optional(), Length(max=120)])
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(min=8, max=128)]
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Create account")


class ProfileForm(FlaskForm):
    display_name = StringField("Display name", validators=[Optional(), Length(max=120)])
    bio = TextAreaField("Short bio", validators=[Optional(), Length(max=1000)])
    avatar = FileField(
        "Avatar (optional)",
        validators=[Optional(), FileAllowed(Config.ALLOWED_IMAGE_EXT, "Image files only.")],
    )
    submit = SubmitField("Save profile")


class PasswordChangeForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField(
        "New password", validators=[DataRequired(), Length(min=8, max=128)]
    )
    confirm = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")],
    )
    submit = SubmitField("Update password")


class CategoryForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=80)])
    kind = SelectField(
        "Applies to",
        choices=[
            ("all", "All sections"),
            ("news", "News articles"),
            ("video", "Videos"),
            ("audio", "Audio"),
            ("ad", "Ads / Marketplace"),
        ],
        default="all",
    )
    description = StringField(
        "Description", validators=[Optional(), Length(max=255)]
    )
    submit = SubmitField("Save category")


class ArticleForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=255)])
    summary = TextAreaField(
        "Short summary (shown in lists)",
        validators=[Optional(), Length(max=500)],
    )
    body = TextAreaField(
        "Article body (Markdown supported)", validators=[DataRequired()]
    )
    cover = FileField(
        "Cover image",
        validators=[Optional(), FileAllowed(Config.ALLOWED_IMAGE_EXT, "Image files only.")],
    )
    remove_cover = BooleanField("Remove current cover image")
    category_id = SelectField("Category", coerce=int, validators=[Optional()])
    tags = StringField(
        "Tags (comma-separated)",
        validators=[Optional(), Length(max=500)],
        description="e.g. politics, takoradi, fishing — keep them short",
    )
    is_featured = BooleanField("Feature on homepage")
    status = SelectField(
        "Status",
        choices=[("draft", "Draft"), ("published", "Published")],
        default="published",
    )
    submit = SubmitField("Save article")


class MediaForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=255)])
    description = TextAreaField("Description", validators=[Optional()])
    kind = SelectField(
        "Type",
        choices=[("video", "Video")],
        default="video",
        validators=[DataRequired()],
    )
    source_type = SelectField(
        "Source",
        choices=[
            ("embed", "Embed from URL (Facebook / YouTube / Vimeo / SoundCloud / Spotify)"),
            ("upload", "Upload a file"),
        ],
        default="embed",
    )
    embed_url = StringField(
        "Embed URL", validators=[Optional(), URL(message="Enter a valid URL."), Length(max=1024)]
    )
    media_file = FileField(
        "Media file",
        validators=[
            Optional(),
            FileAllowed(
                Config.ALLOWED_AUDIO_EXT | Config.ALLOWED_VIDEO_EXT,
                "Allowed: " + ", ".join(sorted(Config.ALLOWED_AUDIO_EXT | Config.ALLOWED_VIDEO_EXT)),
            ),
        ],
    )
    thumbnail = FileField(
        "Thumbnail / cover image",
        validators=[Optional(), FileAllowed(Config.ALLOWED_IMAGE_EXT, "Image files only.")],
    )
    remove_thumbnail = BooleanField("Remove current thumbnail")
    category_id = SelectField("Category", coerce=int, validators=[Optional()])
    is_featured = BooleanField("Feature on homepage")
    status = SelectField(
        "Status",
        choices=[("draft", "Draft"), ("published", "Published")],
        default="published",
    )
    submit = SubmitField("Save")

    def validate(self, extra_validators=None) -> bool:
        if not super().validate(extra_validators=extra_validators):
            return False
        if self.source_type.data == "embed":
            if not (self.embed_url.data or "").strip():
                self.embed_url.errors.append("Embed URL is required when source is Embed.")
                return False
        else:
            has_existing = bool(getattr(self, "_existing_file_path", None))
            uploaded = self.media_file.data and getattr(self.media_file.data, "filename", "")
            if not uploaded and not has_existing:
                self.media_file.errors.append("Please choose a file to upload.")
                return False
        return True


class AdForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=255)])
    description = TextAreaField("Description", validators=[Optional()])
    price = StringField("Price (e.g. 250 or 'Negotiable')", validators=[Optional(), Length(max=64)])
    currency = StringField("Currency", validators=[Optional(), Length(max=8)], default="GHS")
    contact_phone = StringField("Phone", validators=[Optional(), Length(max=64)])
    contact_whatsapp = StringField("WhatsApp", validators=[Optional(), Length(max=64)])
    contact_email = StringField("Email", validators=[Optional(), Email(), Length(max=255)])
    location = StringField("Location", validators=[Optional(), Length(max=120)])
    external_url = StringField(
        "External link (optional)",
        validators=[Optional(), URL(message="Enter a valid URL."), Length(max=512)],
    )
    image = FileField(
        "Image",
        validators=[Optional(), FileAllowed(Config.ALLOWED_IMAGE_EXT, "Image files only.")],
    )
    remove_image = BooleanField("Remove current image")
    category_id = SelectField("Category", coerce=int, validators=[Optional()])
    is_featured = BooleanField("Feature on homepage")
    status = SelectField(
        "Status",
        choices=[("draft", "Draft"), ("published", "Published")],
        default="published",
    )
    submit = SubmitField("Save ad")


class UserAdminForm(FlaskForm):
    display_name = StringField("Display name", validators=[Optional(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    role = SelectField(
        "Role", choices=[("writer", "Writer"), ("admin", "Admin")], default="writer"
    )
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save user")


class UserCreateForm(FlaskForm):
    """Admin-only form to add a new user with any role."""
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=3, max=64)]
    )
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    display_name = StringField(
        "Display name", validators=[Optional(), Length(max=120)]
    )
    role = SelectField(
        "Role", choices=[("writer", "Writer"), ("admin", "Admin")], default="writer"
    )
    is_active = BooleanField("Active", default=True)
    password = PasswordField(
        "Initial password", validators=[DataRequired(), Length(min=8, max=128)]
    )
    submit = SubmitField("Create user")


class DeleteForm(FlaskForm):
    """Empty form used only to render a CSRF-protected delete button."""
    submit = SubmitField("Delete")


class PortraitForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=255)])
    description = TextAreaField(
        "Description (Markdown supported)", validators=[Optional()]
    )
    price = DecimalField(
        "Price (GHS)",
        places=2,
        validators=[DataRequired(), NumberRange(min=1, message="Minimum price is GHS 1.")],
        description="Buyers pay this amount via Paystack to unlock the high-res file.",
    )
    image = FileField(
        "High-resolution image",
        validators=[
            Optional(),
            FileAllowed(
                Config.ALLOWED_PORTRAIT_EXT,
                "Allowed: " + ", ".join(sorted(Config.ALLOWED_PORTRAIT_EXT)),
            ),
        ],
        description="JPG, PNG or WebP. The original is stored privately; a watermarked preview is generated automatically.",
    )
    is_featured = BooleanField("Feature on homepage")
    status = SelectField(
        "Status",
        choices=[("draft", "Draft"), ("published", "Published")],
        default="published",
    )
    submit = SubmitField("Save portrait")


class CheckoutForm(FlaskForm):
    buyer_email = StringField(
        "Email (where we'll send the download link)",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    buyer_name = StringField(
        "Your name (optional)", validators=[Optional(), Length(max=120)]
    )
    submit = SubmitField("Continue to payment")
