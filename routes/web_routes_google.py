"""Google Calendar connect/sync routes."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from flask import Flask, abort, flash, jsonify, redirect, request, session, url_for

import web_context
import web_db
import web_google_calendar as gcal
import web_schedule

try:
    import local_secrets  # type: ignore
except Exception:  # pragma: no cover
    local_secrets = None


def register(app: Flask) -> None:
    @app.route("/api/google_calendar/sync", methods=["POST"])
    def api_google_calendar_sync():
        user = web_context.role_required("student")

        service = gcal.get_calendar_service(int(user["id"]))
        if not service:
            return jsonify({"ok": False, "error": "Google Calendar not connected."}), 400

        payload: dict[str, Any] = request.get_json(silent=True) or {}
        days = int(payload.get("days") or 7)
        days = max(1, min(days, 21))

        tz = os.environ.get("SCHEDULE_TIMEZONE")
        if not tz and local_secrets is not None:
            tz = getattr(local_secrets, "SCHEDULE_TIMEZONE", None)
        if not tz:
            tz = "UTC"

        start = datetime.now().date()
        start_iso = web_schedule.date_to_iso(start)
        end_iso = web_schedule.date_to_iso(start + timedelta(days=days - 1))

        items = web_db.list_schedule_items(user_id=int(user["id"]), start_date=start_iso, end_date=end_iso, limit=500)
        calendar_id = "primary"

        created = 0
        skipped = 0
        failed: list[dict[str, Any]] = []

        for it in items:
            sid = int(it.get("id") or 0)
            if sid <= 0:
                continue

            existing = web_db.get_schedule_google_event(schedule_item_id=sid)
            if existing and existing.get("event_id"):
                skipped += 1
                continue

            d = str(it.get("date") or "")
            st = str(it.get("start_time") or "")
            et = str(it.get("end_time") or "")
            subject = str(it.get("subject") or "")
            task_type = str(it.get("task_type") or "study")
            task_id = it.get("task_id")
            reason = str(it.get("reason") or "")

            if not (d and st and et and subject):
                failed.append({"schedule_item_id": sid, "error": "Missing required fields"})
                continue

            summary = f"{subject} - {task_type}".strip()
            description = f"Task id: {task_id}\nReason: {reason}".strip()

            body = {
                "summary": summary,
                "description": description,
                "start": {"dateTime": f"{d}T{st}:00", "timeZone": tz},
                "end": {"dateTime": f"{d}T{et}:00", "timeZone": tz},
            }

            try:
                ev = service.events().insert(calendarId=calendar_id, body=body).execute()
                event_id = ev.get("id")
                if event_id:
                    web_db.upsert_schedule_google_event(
                        schedule_item_id=sid,
                        calendar_id=calendar_id,
                        event_id=str(event_id),
                    )
                    created += 1
                else:
                    failed.append({"schedule_item_id": sid, "error": "No event id returned"})
            except Exception as e:
                failed.append({"schedule_item_id": sid, "error": str(e)})

        return jsonify({"ok": True, "created": created, "skipped": skipped, "failed": failed})

    @app.route("/google/connect")
    def google_connect():
        user = web_context.role_required("student")
        if not gcal.Flow:
            flash("Google Calendar libraries not installed.")
            return redirect(url_for("chat_home"))

        # Local development: OAuth over HTTP is blocked by oauthlib unless explicitly enabled.
        # Only enable this for localhost/127.0.0.1.
        if request.host.startswith("127.0.0.1") or request.host.startswith("localhost"):
            os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

        config = gcal.load_google_client_config()
        if not config:
            flash("Missing Google OAuth client config. See setup instructions.")
            return redirect(url_for("chat_home"))

        redirect_uri = url_for("google_oauth_callback", _external=True)
        flow = gcal.Flow.from_client_config(
            config,
            scopes=gcal.google_scopes(),
            redirect_uri=redirect_uri,
        )

        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        session["google_oauth_state"] = state
        session["google_oauth_user"] = int(user["id"])
        return redirect(auth_url)

    @app.route("/google/callback")
    def google_oauth_callback():
        user = web_context.login_required()
        if user.get("role") != "student":
            return abort(403)

        if not gcal.Flow:
            return abort(500)

        # Local development: allow OAuth over HTTP for localhost.
        if request.host.startswith("127.0.0.1") or request.host.startswith("localhost"):
            os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

        config = gcal.load_google_client_config()
        if not config:
            flash("Missing Google OAuth client config.")
            return redirect(url_for("chat_home"))

        state = session.get("google_oauth_state")
        if not state:
            flash("Missing OAuth state. Please try again.")
            return redirect(url_for("chat_home"))

        redirect_uri = url_for("google_oauth_callback", _external=True)
        flow = gcal.Flow.from_client_config(
            config,
            scopes=gcal.google_scopes(),
            state=state,
            redirect_uri=redirect_uri,
        )

        try:
            flow.fetch_token(authorization_response=request.url)
        except Exception as e:
            flash(f"Google OAuth failed: {e}")
            return redirect(url_for("chat_home"))

        creds = flow.credentials
        if not creds:
            flash("Google OAuth did not return credentials.")
            return redirect(url_for("chat_home"))

        # Persist token (includes refresh_token on first consent).
        web_db.upsert_google_token(user_id=int(user["id"]), token_json=creds.to_json())
        flash("Google Calendar connected.")
        return redirect(url_for("chat_home"))

    @app.route("/google/disconnect", methods=["POST"])
    def google_disconnect():
        user = web_context.role_required("student")
        web_db.delete_google_token(user_id=int(user["id"]))
        flash("Google Calendar disconnected.")
        return redirect(url_for("chat_home"))
