"""Signup/login/logout routes."""

from __future__ import annotations

import json
import re
from typing import Any

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import web_context
import web_db
from web_constants import ELECTIVE_SUBJECT_CHOICES, INTEREST_CHOICES


def register(app: Flask) -> None:
    def _student_form_from_class_level(v: str) -> int:
        s = (v or "").strip().upper()
        m = re.match(r"^(?:F|FORM)?\s*(\d+)", s)
        if not m:
            return 0
        try:
            return int(m.group(1))
        except Exception:
            return 0

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "GET":
            return render_template(
                "signup.html",
                interest_choices=INTEREST_CHOICES,
                elective_choices=ELECTIVE_SUBJECT_CHOICES,
            )

        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        role = (request.form.get("role") or "student").strip().lower()

        name = (request.form.get("name") or "").strip()
        class_level = (request.form.get("class_level") or "").strip()
        interests = request.form.getlist("interests")
        electives = request.form.getlist("electives")

        if role not in ("student", "teacher"):
            flash("Invalid role.")
            return redirect(url_for("signup"))

        if not email or "@" not in email:
            flash("Please enter a valid email.")
            return redirect(url_for("signup"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.")
            return redirect(url_for("signup"))

        if role == "student":
            if not name:
                flash("Student name is required.")
                return redirect(url_for("signup"))
            if not class_level:
                flash("Student class is required.")
                return redirect(url_for("signup"))

            # Form 4+ students must specify which electives they take.
            form_no = _student_form_from_class_level(class_level)
            electives = [e for e in electives if e in ELECTIVE_SUBJECT_CHOICES]
            if form_no >= 4 and not electives:
                flash("For Form 4+, please select your elective subjects.")
                return redirect(url_for("signup"))

            interests = [i for i in interests if i in INTEREST_CHOICES]
            if len(interests) > 8:
                flash("Please select up to 8 interests.")
                return redirect(url_for("signup"))
        else:
            # Teacher: keep profile fields optional.
            interests = []
            class_level = None
            electives = []

        if web_db.get_user_by_email(email):
            flash("Email already registered. Please log in.")
            return redirect(url_for("login"))

        uid = web_db.create_user(
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            name=name or None,
            class_level=class_level or None,
            electives=electives,
            interests=interests,
        )

        session["user_id"] = uid
        return redirect(url_for("index"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("login.html")

        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = web_db.get_user_by_email(email)
        if not user or not check_password_hash(user.get("password_hash") or "", password):
            flash("Invalid email or password.")
            return redirect(url_for("login"))

        session["user_id"] = int(user["id"])

        # If this is a Form 4+ student without electives saved yet, collect it now.
        if (user.get("role") or "").strip().lower() == "student":
            form_no = _student_form_from_class_level(str(user.get("class_level") or ""))
            if form_no >= 4:
                try:
                    existing = json.loads(user.get("electives_json") or "[]")
                except Exception:
                    existing = []
                if not isinstance(existing, list) or not any(str(x).strip() for x in existing):
                    return redirect(url_for("student_electives"))

        # If the landing prompt stored a pending message, continue into chat.
        if session.get("pending_chat_message"):
            return redirect(url_for("chat_quick"))

        return redirect(url_for("index"))

    @app.route("/electives", methods=["GET", "POST"])
    def student_electives():
        user = web_context.role_required("student")
        class_level = str(user.get("class_level") or "")
        form_no = _student_form_from_class_level(class_level)
        if form_no < 4:
            return redirect(url_for("index"))

        try:
            current = json.loads(user.get("electives_json") or "[]")
            if not isinstance(current, list):
                current = []
        except Exception:
            current = []

        if request.method == "GET":
            return render_template(
                "electives.html",
                elective_choices=ELECTIVE_SUBJECT_CHOICES,
                selected=set([str(x) for x in current if str(x).strip()]),
            )

        electives = [e for e in request.form.getlist("electives") if e in ELECTIVE_SUBJECT_CHOICES]
        if not electives:
            flash("Please select at least one elective subject.")
            return redirect(url_for("student_electives"))

        web_db.set_user_electives(user_id=int(user["id"]), electives=electives)
        flash("Electives updated.")
        return redirect(url_for("index"))

    @app.route("/logout")
    def logout():
        _user = web_context.current_user()
        session.clear()
        return redirect(url_for("login"))
