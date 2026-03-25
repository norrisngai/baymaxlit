"""Teacher routes (view + assignments CRUD)."""

from __future__ import annotations

from datetime import datetime, timedelta

from flask import Flask, current_app, flash, redirect, render_template, request, url_for

import web_context
import web_db


def register(app: Flask) -> None:
    @app.route("/teacher")
    def teacher():
        user = web_context.role_required("teacher")
        # Auto-prune assignments whose deadline is > 7 days past.
        try:
            pruned_ids = web_db.prune_expired_assignments(days_past=7)

            if pruned_ids:
                flash(f"Auto-deleted {len(pruned_ids)} expired task(s) (deadline > 7 days ago).")
        except Exception as e:
            current_app.logger.warning("Assignment auto-prune failed: %s", e)

        students = web_db.list_students()
        assignments = web_db.list_assignments(limit=200)
        return render_template("teacher.html", user=user, students=students, assignments=assignments)

    @app.route("/teacher/assignments/add", methods=["POST"])
    def teacher_add_assignment():
        user = web_context.role_required("teacher")
        item_type = (request.form.get("item_type") or "homework").strip().lower()
        form_number = (request.form.get("form_number") or "").strip()
        class_letter = (request.form.get("class_letter") or "").strip().upper()
        subject = (request.form.get("subject") or "").strip()
        deadline = (request.form.get("deadline") or "").strip()
        description = (request.form.get("description") or "").strip()
        scope = (request.form.get("scope") or "").strip()

        target_class = f"{form_number}{class_letter}" if class_letter else form_number

        if not (form_number and subject and deadline):
            flash("Form, subject, and deadline are required.")
            return redirect(url_for("teacher"))

        try:
            assignment_id = web_db.add_assignment(
                teacher_user_id=int(user["id"]),
                item_type=item_type,
                target_class=target_class,
                subject=subject,
                description=description,
                deadline=deadline,
                scope=scope or None,
            )

            flash("Saved.")
        except Exception as e:
            flash(f"Failed to save: {e}")

        return redirect(url_for("teacher"))

    @app.route("/teacher/assignments/delete", methods=["POST"])
    def teacher_delete_assignment():
        user = web_context.role_required("teacher")
        try:
            assignment_id = int((request.form.get("id") or "0").strip() or "0")
            if assignment_id <= 0:
                flash("Invalid id.")
                return redirect(url_for("teacher"))
            web_db.delete_assignment(assignment_id=assignment_id, teacher_user_id=int(user["id"]))

            flash("Deleted.")
        except Exception as e:
            flash(f"Failed to delete: {e}")
        return redirect(url_for("teacher"))
