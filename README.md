# AhantaPulse News Portal

A Flask-based news portal for the Ahanta region with:

- **News** — Markdown articles with cover images, categories, featured flag, draft/published states.
- **Videos** — embed Facebook, YouTube, Vimeo, or upload `.mp4` / `.webm` / `.mov` files.
- **Audio** — embed SoundCloud or Spotify, or upload `.mp3` / `.m4a` / `.wav` / `.ogg` / `.aac`.
- **Marketplace ads** — title, description, price, phone/WhatsApp/email contacts and an image.
- **Multi-user auth** — admins manage everything; writers register and publish their own content.
- **Search** across articles, media and ads.
- **Email signup** for launch updates (`/api/notify`).

Stack: Flask 3, Flask-SQLAlchemy, Flask-Login, Flask-WTF, SQLite, Tailwind (CDN), Markdown.

---

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Optional: copy a sample env file (see "Configuration" below)
cp .env.example .env  # if you create one

export FLASK_APP=app:app
flask run --debug
```

Open <http://127.0.0.1:5000/>.

On first run the database (`instance/ahantapulse.sqlite3`) is created
automatically and a default admin user + a starter set of categories are
seeded. You can also run it manually:

```bash
flask init-db
```

Sign in at `/auth/login` with the admin credentials from your environment
(defaults are `admin` / `ChangeMe123!` — **change these in production**).

## Configuration

All settings come from environment variables. The defaults are safe for local
development; override them in production.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | `change-me-in-production` | Flask session / CSRF secret. **Set this.** |
| `DATABASE_URL` | `sqlite:///instance/ahantapulse.sqlite3` | SQLAlchemy URL (SQLite only for v1). |
| `MAX_UPLOAD_MB` | `256` | Max upload size in megabytes. |
| `SITE_NAME` | `AhantaPulse` | Site brand name. |
| `SITE_TAGLINE` | `News, voices and stories from the Ahanta` | Hero subtitle. |
| `SITE_REGION` | `Ahanta, Ghana` | Region shown in the header / footer. |
| `CONTACT_EMAIL` | _empty_ | Optional contact email. |
| `ALLOW_REGISTRATION` | `true` | Set to `false` to close public signup. |
| `ADMIN_USERNAME` | `admin` | Seeded admin username (first run only). |
| `ADMIN_EMAIL` | `admin@example.com` | Seeded admin email. |
| `ADMIN_PASSWORD` | `ChangeMe123!` | Seeded admin password. |

Uploaded media is stored under `static/uploads/<kind>/<yyyy>/<mm>/...`. Make
sure this directory is writable by the web server and is excluded from VCS
(it already is, see `.gitignore`).

## Publishing workflow

1. Sign in.
2. From the admin sidebar, choose **Articles**, **Videos & audio**, **Ads**, or
   **Categories**.
3. Click **New** and fill out the form. Markdown is supported for article and
   ad descriptions.
4. For video/audio choose either:
   - **Embed** — paste any Facebook / YouTube / Vimeo / SoundCloud / Spotify URL.
   - **Upload** — upload a file directly. Video gets an HTML5 `<video>` player;
     audio gets a `<audio>` player.
5. Toggle **Featured** to surface content on the homepage hero strip.

Writers see only their own content. Admins see and can edit everything plus
manage categories and users.

## cPanel / Phusion Passenger deployment

1. **Application startup file**: `passenger_wsgi.py`
2. **Application root**: the directory containing the code.
3. **WSGI callable**: `application`.
4. Run `pip install -r requirements.txt` in the app's virtualenv.
5. Set environment variables in cPanel (at minimum `SECRET_KEY`,
   `ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`).
6. Make sure `instance/` and `static/uploads/` are writable by the app user.
7. Restart the app from cPanel. The first request will auto-create the
   database and seed the admin.

### Notes for production

- The current setup loads Tailwind from a CDN. For best performance switch to
  a built CSS file later, but it works fine for typical traffic.
- For large video files, configure your web server's request size limit and
  consider hosting big files elsewhere (or use embeds — Facebook embeds are
  free and unlimited).
- Static uploads can grow quickly; back them up alongside the SQLite file.

## URL map

| Path | Purpose |
| --- | --- |
| `/` | Homepage with featured + latest content. |
| `/news`, `/news/<slug>` | Article list and detail. |
| `/videos`, `/videos/<slug>` | Video list and detail. |
| `/audio`, `/audio/<slug>` | Audio list and detail. |
| `/ads`, `/ads/<slug>` | Marketplace list and detail. |
| `/search?q=...` | Cross-content search. |
| `/auth/login`, `/auth/register`, `/auth/profile` | Account management. |
| `/admin/...` | Admin dashboard and CRUD pages. |
| `/api/info`, `/api/notify`, `/health` | JSON helpers + uptime check. |
