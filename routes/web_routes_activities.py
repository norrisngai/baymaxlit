"""Routes for extracurricular activities (teacher + student)."""

from __future__ import annotations

import json
from flask import Flask, flash, redirect, render_template, request, url_for, jsonify

import web_context
import web_db
from web_constants import ACTIVITY_TAG_CHOICES


def register(app: Flask) -> None:

    # ── Teacher: manage activities ────────────────────────────────────────

    @app.route("/teacher/activities")
    def teacher_activities():
        user = web_context.role_required("teacher")
        activities = web_db.list_activities_by_teacher(teacher_user_id=int(user["id"]))
        # Attach enrollment counts and parsed tags
        for act in activities:
            act["enrolled_count"] = web_db.count_enrolled(activity_id=int(act["id"]))
            act["tags"] = json.loads(act.get("tags_json") or "[]")
        return render_template(
            "teacher_activities.html",
            user=user,
            activities=activities,
            tag_choices=ACTIVITY_TAG_CHOICES,
        )

    @app.route("/teacher/activities/add", methods=["POST"])
    def teacher_add_activity():
        user = web_context.role_required("teacher")
        name = (request.form.get("name") or "").strip()
        activity_type = (request.form.get("activity_type") or "optional").strip()
        tags = request.form.getlist("tags")
        act_date = (request.form.get("date") or "").strip()
        start_time = (request.form.get("start_time") or "").strip()
        end_time = (request.form.get("end_time") or "").strip()
        venue = (request.form.get("venue") or "").strip()

        if not (name and act_date and start_time and end_time and venue):
            flash("All fields are required.")
            return redirect(url_for("teacher_activities"))

        if activity_type not in ("mandatory", "optional"):
            activity_type = "optional"

        # Validate tags against allowed set
        valid_tags = [t for t in tags if t in ACTIVITY_TAG_CHOICES]

        try:
            web_db.create_activity(
                teacher_user_id=int(user["id"]),
                name=name,
                activity_type=activity_type,
                tags=valid_tags,
                date=act_date,
                start_time=start_time,
                end_time=end_time,
                venue=venue,
            )

            # If mandatory, auto-enroll all students
            if activity_type == "mandatory":
                activity_list = web_db.list_activities_by_teacher(teacher_user_id=int(user["id"]))
                new_act = activity_list[-1] if activity_list else None
                if new_act:
                    students = web_db.list_students()
                    for s in students:
                        web_db.enroll_in_activity(activity_id=int(new_act["id"]), user_id=int(s["id"]))
                        # Add to student's schedule
                        web_db.add_schedule_item(
                            user_id=int(s["id"]),
                            date=act_date,
                            start_time=start_time,
                            end_time=end_time,
                            subject=name,
                            task_type="activity",
                            task_id=int(new_act["id"]),
                            reason=f"Mandatory activity: {name}",
                        )

            flash("Activity created.")
        except Exception as e:
            flash(f"Failed to create activity: {e}")

        return redirect(url_for("teacher_activities"))

    @app.route("/teacher/activities/delete", methods=["POST"])
    def teacher_delete_activity():
        user = web_context.role_required("teacher")
        try:
            activity_id = int((request.form.get("id") or "0").strip() or "0")
            if activity_id <= 0:
                flash("Invalid id.")
                return redirect(url_for("teacher_activities"))

            # Remove schedule items linked to this activity for all users
            act = web_db.get_activity(activity_id=activity_id)
            if act and int(act["teacher_user_id"]) == int(user["id"]):
                enrolled = web_db.list_enrolled_students(activity_id=activity_id)
                for s in enrolled:
                    # Delete matching schedule items
                    items = web_db.list_schedule_items(user_id=int(s["id"]))
                    for item in items:
                        if item.get("task_type") == "activity" and item.get("task_id") == activity_id:
                            web_db.delete_schedule_item(user_id=int(s["id"]), schedule_item_id=int(item["id"]))

            web_db.delete_activity(activity_id=activity_id, teacher_user_id=int(user["id"]))
            flash("Activity deleted.")
        except Exception as e:
            flash(f"Failed to delete: {e}")
        return redirect(url_for("teacher_activities"))

    @app.route("/teacher/activities/<int:activity_id>/students")
    def teacher_activity_students(activity_id: int):
        user = web_context.role_required("teacher")
        act = web_db.get_activity(activity_id=activity_id)
        if not act or int(act["teacher_user_id"]) != int(user["id"]):
            flash("Activity not found.")
            return redirect(url_for("teacher_activities"))
        students = web_db.list_enrolled_students(activity_id=activity_id)
        act["tags"] = json.loads(act.get("tags_json") or "[]")
        return render_template(
            "teacher_activity_students.html",
            user=user,
            activity=act,
            students=students,
        )

    # ── Student: browse & join activities ─────────────────────────────────

    @app.route("/activities")
    def student_activities():
        user = web_context.role_required("student")
        user_id = int(user["id"])
        user_interests = json.loads(user.get("interests_json") or "[]")
        enrolled_ids = set(web_db.list_student_enrollments(user_id=user_id))

        all_activities = web_db.list_all_activities()

        recommended = []
        other = []
        mandatory = []

        for act in all_activities:
            act["tags"] = json.loads(act.get("tags_json") or "[]")
            act["enrolled"] = act["id"] in enrolled_ids
            act["enrolled_count"] = web_db.count_enrolled(activity_id=int(act["id"]))

            if act["activity_type"] == "mandatory":
                mandatory.append(act)
            else:
                # Check tag overlap with student interests
                overlap = set(act["tags"]) & set(user_interests)
                act["relevance"] = len(overlap)
                if overlap:
                    recommended.append(act)
                else:
                    other.append(act)

        # Sort recommended by relevance (most matching tags first)
        recommended.sort(key=lambda a: -a["relevance"])

        return render_template(
            "activities.html",
            user=user,
            mandatory=mandatory,
            recommended=recommended,
            other=other,
        )

    @app.route("/activities/join", methods=["POST"])
    def join_activity():
        user = web_context.role_required("student")
        user_id = int(user["id"])
        activity_id = int((request.form.get("activity_id") or "0").strip() or "0")

        if activity_id <= 0:
            flash("Invalid activity.")
            return redirect(url_for("student_activities"))

        act = web_db.get_activity(activity_id=activity_id)
        if not act:
            flash("Activity not found.")
            return redirect(url_for("student_activities"))

        # Check time conflicts
        conflicts = web_db.check_schedule_conflict(
            user_id=user_id,
            date=act["date"],
            start_time=act["start_time"],
            end_time=act["end_time"],
        )
        if conflicts:
            conflict_names = [c.get("subject", "Unknown") for c in conflicts]
            flash(f"Time conflict with: {', '.join(conflict_names)}. Please resolve the conflict first.")
            return redirect(url_for("student_activities"))

        newly_enrolled = web_db.enroll_in_activity(activity_id=activity_id, user_id=user_id)
        if newly_enrolled:
            # Add to the student's schedule
            web_db.add_schedule_item(
                user_id=user_id,
                date=act["date"],
                start_time=act["start_time"],
                end_time=act["end_time"],
                subject=act["name"],
                task_type="activity",
                task_id=activity_id,
                reason=f"Activity: {act['name']}",
            )
            flash(f"Joined '{act['name']}'!")
        else:
            flash("Already joined this activity.")

        return redirect(url_for("student_activities"))

    @app.route("/activities/leave", methods=["POST"])
    def leave_activity():
        user = web_context.role_required("student")
        user_id = int(user["id"])
        activity_id = int((request.form.get("activity_id") or "0").strip() or "0")

        if activity_id <= 0:
            flash("Invalid activity.")
            return redirect(url_for("student_activities"))

        act = web_db.get_activity(activity_id=activity_id)
        if not act:
            flash("Activity not found.")
            return redirect(url_for("student_activities"))

        if act["activity_type"] == "mandatory":
            flash("Cannot leave a mandatory activity.")
            return redirect(url_for("student_activities"))

        web_db.unenroll_from_activity(activity_id=activity_id, user_id=user_id)

        # Remove matching schedule item
        items = web_db.list_schedule_items(user_id=user_id)
        for item in items:
            if item.get("task_type") == "activity" and item.get("task_id") == activity_id:
                web_db.delete_schedule_item(user_id=user_id, schedule_item_id=int(item["id"]))

        flash(f"Left '{act['name']}'.")
        return redirect(url_for("student_activities"))
