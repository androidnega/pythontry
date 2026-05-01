# AhantaPulse Freelance Hub

Minimal Flask landing page: clients and freelancers in Ahanta. MySQL connection helpers are in `app.py` for when you add a database; `/api/info` and `/api/time` work without MySQL.

## cPanel / Passenger

1. Application startup file: `passenger_wsgi.py` — WSGI callable: `application`
2. `pip install -r requirements.txt`
3. Set `SECRET_KEY` and optional MySQL env vars: `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`

## Local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=app:app
flask run --debug
```

Open http://127.0.0.1:5000/ — `/health` returns `ok`.
