"""Profile routes (coins + basic user info)."""

from __future__ import annotations

import re

from flask import Flask, render_template

import web_context
import web_db


def register(app: Flask) -> None:
    @app.route("/profile")
    def profile():
        user = web_context.login_required()

        def norm_subject(value: str) -> str:
            return re.sub(r"\s+", " ", (value or "").strip()).lower()

        try:
            coins = int(user.get("coins") or 0)
        except Exception:
            coins = 0
            
        user_id = int(user.get("id"))
        
        # Study time progress
        study_seconds = web_db.get_today_study_seconds(user_id)
        # Assuming 2 hours (7200 seconds) is full capacity
        study_hours = study_seconds / 3600.0
        study_progress_percent = min(100, int((study_seconds / 7200) * 100))
        
        # Upcoming schedule (limit 3)
        upcoming_schedules = web_db.get_upcoming_schedule_items_for_profile(user_id, limit=3)
        
        subject_performance_rows = web_db.get_quiz_subject_performance(user_id=user_id)
        allowed_subjects = web_context.student_allowed_subjects(user)
        if allowed_subjects:
            subject_performance_rows = [
                row for row in subject_performance_rows
                if norm_subject(str(row.get("subject") or "")) in allowed_subjects
            ]

        profile_subject_metrics = [
            {
                "subject": str(row.get("subject") or "General"),
                "score_percent": float(row.get("avg_percent") or 0.0),
                "attempts": int(row.get("attempts") or 0),
            }
            for row in subject_performance_rows
        ]

        strongest_subject = None
        weakest_subject = None
        subject_average_percent = None
        if profile_subject_metrics:
            strongest_subject = max(profile_subject_metrics, key=lambda item: item["score_percent"])
            weakest_subject = min(profile_subject_metrics, key=lambda item: item["score_percent"])
            subject_average_percent = round(
                sum(item["score_percent"] for item in profile_subject_metrics) / len(profile_subject_metrics),
                1,
            )
        
        return render_template(
            "profile.html", 
            user=user, 
            coins=coins,
            study_hours=study_hours,
            study_progress_percent=study_progress_percent,
            upcoming_schedules=upcoming_schedules,
            profile_subject_metrics=profile_subject_metrics,
            strongest_subject=strongest_subject,
            weakest_subject=weakest_subject,
            subject_average_percent=subject_average_percent,
        )
