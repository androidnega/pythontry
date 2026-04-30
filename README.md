# Calculator

- **Desktop:** `calculator.py` (Tkinter) — same logic as the web app.
- **Web (cPanel / Passenger):** Flask app in `app.py`, WSGI entry `passenger_wsgi.py`, logic in `calculator_core.py`. The UI is server-rendered HTML (no client-side JavaScript); each button submits the form so all work runs in Python.

## cPanel setup

1. Upload this entire project folder to your **application root** (the directory cPanel assigns to the Python app).
2. In **Setup Python App**, create an app and install dependencies, for example:
   - `pip install -r requirements.txt`
3. Configure the app (exact labels vary by host):
   - **Application startup file:** `passenger_wsgi.py`
   - **Application Entry point / WSGI callable:** `application`
4. Set environment variable **`SECRET_KEY`** in the panel (or in `passenger_wsgi.py` / app config) to a long random string for production.
5. Restart the application from cPanel after changes.

If your host expects a different startup filename or callable name, follow their documentation and adjust `passenger_wsgi.py` or `app.py` accordingly.

## Local run (web)

```bash
cd "/path/to/this/folder"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=app:app
flask run --debug
```

Open http://127.0.0.1:5000/ — `GET /health` returns `ok`.

## Local run (desktop)

```bash
python3 calculator.py
```
