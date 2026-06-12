"""WTForms forms used by auth and admin blueprints."""

from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, MultipleFileField
from wtforms import (
    BooleanField,
    DecimalField,
    IntegerField,
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
        "Main high-resolution image",
        validators=[
            Optional(),
            FileAllowed(
                Config.ALLOWED_PORTRAIT_EXT,
                "Allowed: " + ", ".join(sorted(Config.ALLOWED_PORTRAIT_EXT)),
            ),
        ],
        description="JPG, PNG or WebP. The original is stored privately; a watermarked preview is generated automatically.",
    )
    extra_images = MultipleFileField(
        "Additional views (optional)",
        validators=[
            Optional(),
            FileAllowed(
                Config.ALLOWED_PORTRAIT_EXT,
                "Allowed: " + ", ".join(sorted(Config.ALLOWED_PORTRAIT_EXT)),
            ),
        ],
        description="Add up to 5 more shots — close-ups, alternate angles, behind-the-scenes — so buyers can see the work from every side.",
    )
    card_aspect = SelectField(
        "Card shape",
        choices=[
            ("natural", "Match image (no crop)"),
            ("1:1", "Square (1:1)"),
            ("4:5", "Portrait (4:5)"),
            ("3:4", "Portrait (3:4)"),
            ("4:3", "Landscape (4:3)"),
            ("16:9", "Landscape (16:9)"),
        ],
        default="natural",
        description="How portrait cards display on the home page, list and related sections.",
    )
    focal_x = IntegerField(
        "Focal X",
        default=50,
        validators=[Optional(), NumberRange(min=0, max=100)],
    )
    focal_y = IntegerField(
        "Focal Y",
        default=50,
        validators=[Optional(), NumberRange(min=0, max=100)],
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


class SmtpSettingsForm(FlaskForm):
    """Admin form for SMTP credentials used to email subscribers."""
    enabled = BooleanField("Enable email sending")
    host = StringField("SMTP host", validators=[Optional(), Length(max=255)])
    port = IntegerField(
        "SMTP port",
        validators=[Optional(), NumberRange(min=1, max=65535)],
        default=587,
    )
    username = StringField("SMTP username", validators=[Optional(), Length(max=255)])
    password = PasswordField(
        "SMTP password (leave blank to keep existing)",
        validators=[Optional(), Length(max=255)],
    )
    use_tls = BooleanField("Use STARTTLS (recommended on port 587)", default=True)
    use_ssl = BooleanField("Use SSL (typical on port 465)")
    from_email = StringField(
        "From email address",
        validators=[Optional(), Email(), Length(max=255)],
    )
    from_name = StringField(
        "From display name", validators=[Optional(), Length(max=120)]
    )
    submit = SubmitField("Save SMTP settings")


class CommentForm(FlaskForm):
    """Reader comment form — works for logged-in users and guests.

    `author_name` and `author_email` are only required when no one is
    logged in (enforced in the view, since FlaskForm validators don't
    have request context). `website` is a hidden honeypot field that
    must stay empty; bots fill it and we silently drop those.
    """
    author_name = StringField("Your name", validators=[Optional(), Length(max=120)])
    author_email = StringField("Email (optional, not published)",
                               validators=[Optional(), Email(), Length(max=255)])
    body = TextAreaField(
        "Your comment",
        validators=[DataRequired(), Length(min=2, max=4000)],
    )
    # Honeypot: real humans leave this blank.
    website = StringField("Website", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Post comment")


class TinymceSettingsForm(FlaskForm):
    """Admin form to paste / rotate the TinyMCE Cloud API key."""
    api_key = StringField(
        "TinyMCE API key",
        validators=[Optional(), Length(max=128)],
        description="Get a free key at tiny.cloud and add ahantapulse.online to its allowed domains.",
    )
    submit_tinymce = SubmitField("Save editor key")


class AiSettingsForm(FlaskForm):
    """Admin form for the AI writing assistant (DeepSeek / OpenAI-compatible)."""
    api_key = PasswordField(
        "API key (leave blank to keep existing)",
        validators=[Optional(), Length(max=255)],
        description="Get a key at platform.deepseek.com or platform.openai.com.",
    )
    base = StringField(
        "API base URL",
        validators=[Optional(), Length(max=255)],
        default="https://api.deepseek.com/v1",
        description="DeepSeek: https://api.deepseek.com/v1   ·   OpenAI: https://api.openai.com/v1",
    )
    model = StringField(
        "Model",
        validators=[Optional(), Length(max=80)],
        default="deepseek-chat",
        description="DeepSeek: deepseek-chat   ·   OpenAI: gpt-4o-mini, gpt-4o, etc.",
    )
    max_tokens = IntegerField(
        "Max tokens per request",
        validators=[Optional(), NumberRange(min=256, max=8000)],
        default=1800,
    )
    submit_ai = SubmitField("Save AI settings")


class GoogleOAuthSettingsForm(FlaskForm):
    """Admin form for Sign-in with Google (OAuth 2.0 / OIDC)."""
    client_id = StringField(
        "Client ID",
        validators=[Optional(), Length(max=255)],
        description="The OAuth 2.0 Client ID from console.cloud.google.com (Credentials).",
    )
    client_secret = PasswordField(
        "Client secret (leave blank to keep existing)",
        validators=[Optional(), Length(max=255)],
    )
    submit_google = SubmitField("Save Google sign-in")


class TestEmailForm(FlaskForm):
    to_addr = StringField(
        "Send a test email to",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    submit = SubmitField("Send test")
