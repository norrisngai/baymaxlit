"""Study timer + coins routes.

Awards +10 coins for every 30 minutes of active study timer time.
Server-side timekeeping is authoritative.
"""

from __future__ import annotations

from typing import Any, Optional

from flask import Flask, jsonify

import web_context
import web_db


def register(app: Flask) -> None:
    def _require_schedule_link(*, user_id: int, chat_id: int) -> Optional[int]:
        """Return schedule_item_id if this revision chat is schedule-linked; else None."""
        try:
            sess = web_db.get_revision_session_for_user_by_chat_id(user_id=int(user_id), chat_id=int(chat_id))
        except Exception:
            sess = None
        if not sess:
            return None
        try:
            schedule_item_id = int(sess.get("schedule_item_id") or 0)
        except Exception:
            schedule_item_id = 0
        return schedule_item_id if schedule_item_id > 0 else None

    @app.get("/api/study-timer/<int:chat_id>/status")
    def api_study_timer_status(chat_id: int):
        user = web_context.role_required("student")
        schedule_item_id = _require_schedule_link(user_id=int(user["id"]), chat_id=chat_id)
        if not schedule_item_id:
            return jsonify(ok=False, error="Timer is only available for schedule-linked Study with me sessions."), 400

        try:
            status = web_db.get_study_timer_status(
                user_id=int(user["id"]),
                chat_id=int(chat_id),
                schedule_item_id=int(schedule_item_id),
            )
            return jsonify(ok=True, **status)
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500

    @app.post("/api/study-timer/<int:chat_id>/start")
    def api_study_timer_start(chat_id: int):
        user = web_context.role_required("student")
        schedule_item_id = _require_schedule_link(user_id=int(user["id"]), chat_id=chat_id)
        if not schedule_item_id:
            return jsonify(ok=False, error="Timer is only available for schedule-linked Study with me sessions."), 400

        try:
            status = web_db.start_study_timer(
                user_id=int(user["id"]),
                chat_id=int(chat_id),
                schedule_item_id=int(schedule_item_id),
            )
            return jsonify(ok=True, **status)
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500

    @app.post("/api/study-timer/<int:chat_id>/pause")
    def api_study_timer_pause(chat_id: int):
        user = web_context.role_required("student")
        schedule_item_id = _require_schedule_link(user_id=int(user["id"]), chat_id=chat_id)
        if not schedule_item_id:
            return jsonify(ok=False, error="Timer is only available for schedule-linked Study with me sessions."), 400

        try:
            status = web_db.pause_study_timer(
                user_id=int(user["id"]),
                chat_id=int(chat_id),
                schedule_item_id=int(schedule_item_id),
            )
            return jsonify(ok=True, **status)
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500

    @app.post("/api/study-timer/<int:chat_id>/tick")
    def api_study_timer_tick(chat_id: int):
        """Heartbeat endpoint.

        The client should call this periodically while running to trigger coin awards.
        """
        user = web_context.role_required("student")
        schedule_item_id = _require_schedule_link(user_id=int(user["id"]), chat_id=chat_id)
        if not schedule_item_id:
            return jsonify(ok=False, error="Timer is only available for schedule-linked Study with me sessions."), 400

        try:
            status = web_db.get_study_timer_status(
                user_id=int(user["id"]),
                chat_id=int(chat_id),
                schedule_item_id=int(schedule_item_id),
            )
            return jsonify(ok=True, **status)
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500
