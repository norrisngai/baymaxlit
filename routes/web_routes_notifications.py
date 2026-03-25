"""Notification routes."""

from __future__ import annotations

from flask import Flask, jsonify, request

import web_context
import web_db


def register(app: Flask) -> None:
    @app.route("/api/notifications")
    def api_notifications_list():
        """Get list of notifications for current user."""
        user = web_context.role_required("student")
        user_id = int(user["id"])
        
        unread_only = request.args.get("unread_only", "false").lower() == "true"
        notifications = web_db.list_notifications(user_id=user_id, unread_only=unread_only)
        
        return jsonify(ok=True, notifications=notifications)

    @app.route("/api/notifications/count")
    def api_notifications_count():
        """Get unread notification count."""
        user = web_context.role_required("student")
        user_id = int(user["id"])
        
        count = web_db.get_unread_notification_count(user_id=user_id)
        return jsonify(ok=True, count=count)

    @app.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
    def api_notification_mark_read(notification_id: int):
        """Mark a notification as read."""
        user = web_context.role_required("student")
        user_id = int(user["id"])
        
        web_db.mark_notification_read(notification_id=notification_id, user_id=user_id)
        return jsonify(ok=True)

    @app.route("/api/notifications/<int:notification_id>/delete", methods=["POST"])
    def api_notification_delete(notification_id: int):
        """Delete a notification."""
        user = web_context.role_required("student")
        user_id = int(user["id"])
        
        web_db.delete_notification(notification_id=notification_id, user_id=user_id)
        return jsonify(ok=True)

    @app.route("/api/notifications/read-all", methods=["POST"])
    def api_notifications_mark_all_read():
        """Mark all notifications as read."""
        user = web_context.role_required("student")
        user_id = int(user["id"])
        
        web_db.mark_all_notifications_read(user_id=user_id)
        return jsonify(ok=True)

    @app.route("/api/notifications/check", methods=["POST"])
    def api_notifications_check():
        """Manually trigger notification check (admin/debug only)."""
        count = web_db.check_and_create_deadline_notifications()
        return jsonify(ok=True, notifications_created=count)
