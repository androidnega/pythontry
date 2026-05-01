"""AhantaPulse Freelance Hub — Flask entry (WSGI: application)."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import mysql.connector
from flask import Flask, jsonify, render_template

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-in-production")
application = app


def get_mysql_connection():
    """Open a MySQL connection from env (optional until you add a database)."""
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", ""),
        database=os.environ.get("MYSQL_DATABASE", "ahantapulse"),
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/info")
def api_info():
    return jsonify(
        name="AhantaPulse Freelance Hub",
        region="Ahanta, Ghana",
        status="preview",
        message="Simple endpoints work without MySQL; connect DB when ready.",
    )


@app.get("/api/time")
def api_time():
    return jsonify(utc=datetime.now(timezone.utc).isoformat())


@app.get("/health")
def health():
    return "ok", 200
