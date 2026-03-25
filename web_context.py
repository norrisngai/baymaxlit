"""Request-scoped helpers for the Flask web app.

Goal: keep common auth/session helpers out of route modules.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from flask import abort, session

import web_db
from web_constants import CORE_SUBJECT_CHOICES, ELECTIVE_SUBJECT_CHOICES


def current_user() -> Optional[dict[str, Any]]:
    uid = session.get("user_id")
    if not uid:
        return None
    return web_db.get_user(int(uid))


def login_required() -> dict[str, Any]:
    user = current_user()
    if not user:
        return abort(401)
    return user


def role_required(role: str) -> dict[str, Any]:
    user = login_required()
    if user.get("role") != role:
        return abort(403)
    return user


def student_form_from_class_level(class_level: str) -> int:
    s = (class_level or "").strip().upper()
    m = re.match(r"^(?:F|FORM)?\s*(\d+)", s)
    if not m:
        return 0
    try:
        return int(m.group(1))
    except Exception:
        return 0


def student_electives(user: dict[str, Any]) -> list[str]:
    raw = user.get("electives_json")
    if not raw:
        return []
    try:
        vals = json.loads(raw)
        if not isinstance(vals, list):
            return []
        return [str(x) for x in vals if str(x).strip()]
    except Exception:
        return []


def student_allowed_subjects(user: dict[str, Any]) -> Optional[set[str]]:
    """Returns None if no filtering should be applied.

    For Form 4+, returns core + electives selected by the student.
    """

    if (user.get("role") or "").strip().lower() != "student":
        return None

    class_level = str(user.get("class_level") or "").strip()
    form_no = student_form_from_class_level(class_level)
    if form_no < 4:
        return None

    electives = student_electives(user)
    allowed = list(CORE_SUBJECT_CHOICES) + electives

    def norm(v: str) -> str:
        return re.sub(r"\s+", " ", (v or "").strip()).lower()

    # Only allow known subjects + whatever electives the student picked (still normalized).
    known = set([norm(x) for x in (CORE_SUBJECT_CHOICES + ELECTIVE_SUBJECT_CHOICES)])
    out: set[str] = set()
    for s in allowed:
        ns = norm(s)
        if ns:
            # If student picked something outside known list, still keep it (for backward-compat).
            out.add(ns)
            known.add(ns)
    return out


def filter_assignments_for_student(
    *,
    user: dict[str, Any],
    assignments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    allowed = student_allowed_subjects(user)
    if not allowed:
        return assignments

    def norm(v: str) -> str:
        return re.sub(r"\s+", " ", (v or "").strip()).lower()

    out: list[dict[str, Any]] = []
    for a in assignments or []:
        subj = norm(str(a.get("subject") or ""))
        if not subj:
            continue
        if subj in allowed:
            out.append(a)
    return out
