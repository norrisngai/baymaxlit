"""Core (landing) routes."""

from __future__ import annotations

from flask import Flask, redirect, render_template, url_for

import web_context


def register(app: Flask) -> None:
    @app.route("/")
    def index():
        user = web_context.current_user()
        if user and user.get("role") == "teacher":
            return redirect(url_for("teacher"))

        # Landing page for students (and guests).
        # The prompt redirects to chat if logged in, otherwise to login.
        chat_url = url_for("chat_home") if user else url_for("login")
        return render_template("landing.html", chat_url=chat_url)
