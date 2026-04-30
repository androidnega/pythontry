"""Flask WSGI application for cPanel / Phusion Passenger."""

from __future__ import annotations

import os

from flask import Flask, render_template, request

from calculator_core import CalculatorState

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-in-production")

# Passenger and many WSGI servers look for `application`
application = app


def _parse_act(raw: str | None) -> tuple[str, str] | None:
    if not raw or ":" not in raw:
        return None
    kind, _, key = raw.partition(":")
    if kind not in ("num", "op", "eq", "clear", "back"):
        return None
    return kind, key


@app.route("/", methods=["GET", "POST"])
def calculator() -> str:
    if request.method == "POST":
        state = CalculatorState.from_form({k: (v or "") for k, v in request.form.items()})
        act = _parse_act(request.form.get("act"))
        if act:
            kind, key = act
            state.dispatch(key, kind)
    else:
        state = CalculatorState()
    return render_template("calculator.html", state=state)


@app.get("/health")
def health() -> tuple[str, int]:
    return "ok", 200
