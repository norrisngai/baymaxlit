"""Student schedule JSON APIs (manual CRUD, generate, chat, study guide)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Flask, current_app, jsonify, request

import web_context
import web_db
import web_schedule


def register(app: Flask) -> None:
    @app.route("/api/schedule/manual/add", methods=["POST"])
    def api_schedule_manual_add():
        user = web_context.role_required("student")
        payload: dict[str, Any] = request.get_json(silent=True) or {}

        d = (payload.get("date") or "").strip()
        st = (payload.get("start_time") or "").strip()
        et = (payload.get("end_time") or "").strip()
        subject = (payload.get("subject") or "").strip()
        task_type = (payload.get("task_type") or "study").strip().lower()

        if not (web_schedule.is_iso_date(d) and web_schedule.is_hhmm(st) and web_schedule.is_hhmm(et) and subject):
            return jsonify({"ok": False, "error": "Missing/invalid date, times, or subject"}), 400

        # Allow any planning: store label in subject; task_type is constrained by DB.
        if task_type not in {"homework", "quiz", "test", "exam", "study"}:
            task_type = "study"

        sid = web_db.add_schedule_item(
            user_id=int(user["id"]),
            date=d,
            start_time=st,
            end_time=et,
            subject=subject,
            task_type=task_type,
            task_id=None,
            reason="Planned by student",
        )
        return jsonify({"ok": True, "id": sid})

    @app.route("/api/schedule/manual/update", methods=["POST"])
    def api_schedule_manual_update():
        user = web_context.role_required("student")
        payload: dict[str, Any] = request.get_json(silent=True) or {}
        sid = int(payload.get("id") or 0)
        patch = payload.get("patch") or {}
        if sid <= 0 or not isinstance(patch, dict):
            return jsonify({"ok": False, "error": "Missing id or patch"}), 400

        # Validate patch fields.
        if "date" in patch and not web_schedule.is_iso_date(str(patch.get("date") or "")):
            return jsonify({"ok": False, "error": "Invalid date"}), 400
        if "start_time" in patch and not web_schedule.is_hhmm(str(patch.get("start_time") or "")):
            return jsonify({"ok": False, "error": "Invalid start time"}), 400
        if "end_time" in patch and not web_schedule.is_hhmm(str(patch.get("end_time") or "")):
            return jsonify({"ok": False, "error": "Invalid end time"}), 400
        if "subject" in patch and not str(patch.get("subject") or "").strip():
            return jsonify({"ok": False, "error": "Subject cannot be empty"}), 400
        if "task_type" in patch:
            tt = str(patch.get("task_type") or "").strip().lower()
            patch["task_type"] = tt if tt in {"homework", "quiz", "test", "exam", "study"} else "study"

        ok = web_db.update_schedule_item(user_id=int(user["id"]), schedule_item_id=sid, patch=patch)
        return jsonify({"ok": bool(ok)})

    @app.route("/api/schedule/manual/delete", methods=["POST"])
    def api_schedule_manual_delete():
        user = web_context.role_required("student")
        payload: dict[str, Any] = request.get_json(silent=True) or {}
        sid = int(payload.get("id") or 0)
        if sid <= 0:
            return jsonify({"ok": False, "error": "Missing id"}), 400

        # Before deleting, get the item's details to inform the AI.
        item_before_delete = web_db.get_schedule_item_for_user(user_id=int(user["id"]), schedule_item_id=sid)

        ok = web_db.delete_schedule_item(user_id=int(user["id"]), schedule_item_id=sid)

        # If deleted and it was an AI-planned item, inform the schedule chatbot.
        if ok and item_before_delete and "Planned by AI" in (item_before_delete.get("reason") or ""):
            try:
                chat_id = web_schedule.get_or_create_schedule_chat_id(int(user["id"]))
                web_db.add_message(
                    chat_id=chat_id,
                    role="assistant",
                    content=(
                        f"(System) User manually deleted this AI-planned session: "
                        f"{item_before_delete.get('date')} "
                        f"{item_before_delete.get('start_time')}-{item_before_delete.get('end_time')} "
                        f"for {item_before_delete.get('subject')}. "
                        f"Do not assume it still exists."
                    ),
                )
            except Exception:
                pass  # Don't fail the delete request if chat update fails

        return jsonify({"ok": bool(ok)})

    @app.route("/api/schedule/chat/send", methods=["POST"])
    def api_schedule_chat_send():
        user = web_context.role_required("student")
        payload: dict[str, Any] = request.get_json(silent=True) or {}
        chat_id = int(payload.get("chat_id") or 0)
        text = (payload.get("message") or "").strip()
        if chat_id <= 0 or not text:
            return jsonify({"ok": False, "error": "Missing chat_id or message"}), 400

        chat_row = web_db.get_chat(chat_id=chat_id, user_id=int(user["id"]))
        if not chat_row or chat_row.get("chat_type") != "schedule":
            return jsonify({"ok": False, "error": "Chat not found"}), 404

        try:
            reply, changed = web_schedule.schedule_edit_reply(
                user=user,
                chat_id=chat_id,
                user_text=text,
                client=current_app.config.get("GEMINI_CLIENT"),
                types=current_app.config.get("GEMINI_TYPES"),
                model_name=current_app.config.get("GEMINI_MODEL_NAME"),
            )
        except Exception as e:
            return jsonify({"ok": False, "error": f"Schedule chat failed: {e}"}), 500

        return jsonify({"ok": True, "reply": reply, "changed": changed})

    @app.route("/api/schedule", methods=["GET"])
    def api_schedule_list():
        user = web_context.role_required("student")
        start_date = (request.args.get("start") or "").strip() or None
        end_date = (request.args.get("end") or "").strip() or None
        items = web_db.list_schedule_items(user_id=int(user["id"]), start_date=start_date, end_date=end_date, limit=500)
        return jsonify({"ok": True, "items": items})

    @app.route("/api/schedule/generate", methods=["POST"])
    def api_schedule_generate():
        user = web_context.role_required("student")
        payload: dict[str, Any] = request.get_json(silent=True) or {}

        days = int(payload.get("days") or 30)
        # Safety guard only (prevents accidental huge requests).
        days = max(1, min(days, 366))

        # Tasks only for student's class.
        class_level = (user.get("class_level") or "").strip()
        if not class_level:
            return jsonify({"ok": False, "error": "Missing student class_level"}), 400

        # SQLite is the source of truth.
        assignments = web_db.get_upcoming_assignments_for_class(target_class=class_level, limit=200)
        assignments = web_context.filter_assignments_for_student(user=user, assignments=assignments)

        # Debug: log assignment count
        print(f"[GENERATE] Found {len(assignments)} assignments for class {class_level}")

        if not assignments:
            return jsonify({"ok": False, "error": f"No assignments found for class {class_level}"}), 400

        try:
            items = web_schedule.generate_schedule_items(
                user=user,
                assignments=assignments,
                days=days,
                client=current_app.config.get("GEMINI_CLIENT"),
                types=current_app.config.get("GEMINI_TYPES"),
                model_name=current_app.config.get("GEMINI_MODEL_NAME"),
            )
            print(f"[GENERATE] AI generated {len(items)} schedule items")
        except Exception as e:
            print(f"[GENERATE ERROR] {e}")
            import traceback

            traceback.print_exc()
            return jsonify({"ok": False, "error": f"Failed to generate schedule: {e}"}), 400

        if not items:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "No sessions could be generated. This usually means there is no free time in your saved planning windows (Schedule settings → availability) or everything conflicts with fixed events.",
                    }
                ),
                400,
            )

        # Only clear existing AI timetable once we have a replacement.
        # This does NOT touch manual items ("Planned by student") or chat items ("Planned via chat").
        try:
            web_db.clear_ai_schedule_items(user_id=int(user["id"]))
        except Exception:
            pass

        web_db.add_schedule_items(user_id=int(user["id"]), items=items)

        # Use the in-memory inserted items first (they may include AI-provided `topics` for study sessions).
        items_for_precompute = items

        # Precompute revision subtopics per study session at generation time.
        # This makes the schedule drawer instant (no AI calls on click) and avoids overlap across sessions.
        try:
            from web_study_guide import generate_topics_plan

            def _student_form_from_class_level(v: str) -> int:
                s = (v or "").strip()
                m = None
                for ch in s:
                    if ch.isdigit():
                        m = ch
                        break
                try:
                    return int(m) if m else 5
                except Exception:
                    return 5

            student_form = _student_form_from_class_level(str(user.get("class_level") or ""))

            # Build lookup for assignment scope/subject.
            by_aid: dict[int, dict[str, Any]] = {}
            for a in assignments:
                try:
                    aid = int(a.get("id") or 0)
                except Exception:
                    continue
                if aid > 0:
                    by_aid[aid] = a

            # Group inserted study sessions by assignment id.
            sessions_by_aid: dict[int, list[dict[str, Any]]] = {}
            for it in items_for_precompute:
                try:
                    sid = int(it.get("id") or 0)
                except Exception:
                    sid = 0
                if sid <= 0:
                    continue
                tt = str(it.get("task_type") or "").strip().lower()
                if tt != "study":
                    continue
                # If AI already provided topics, treat this session as precomputed and skip later AI topic planning.
                raw_topics = it.get("topics")
                if isinstance(raw_topics, list) and any(str(x).strip() for x in raw_topics):
                    # We'll still group by task_id/subject for renaming + persistence below.
                    pass
                try:
                    aid = int(it.get("task_id") or 0)
                except Exception:
                    aid = 0
                if aid <= 0:
                    continue
                sessions_by_aid.setdefault(aid, []).append(it)

            for aid, sess_items in sessions_by_aid.items():
                sess_items.sort(
                    key=lambda x: (
                        str(x.get("date") or ""),
                        str(x.get("start_time") or ""),
                        int(x.get("id") or 0),
                    )
                )
                session_count = max(1, len(sess_items))

                a = by_aid.get(aid) or {}
                subject = (str(a.get("subject") or "").strip() or str(sess_items[0].get("subject") or "").strip() or "Study")
                scope = (str(a.get("scope") or "").strip() or str(a.get("description") or "").strip() or subject)

                session_schedule = [
                    {
                        "id": int(s.get("id") or 0),
                        "date": str(s.get("date") or ""),
                        "start_time": str(s.get("start_time") or ""),
                        "end_time": str(s.get("end_time") or ""),
                    }
                    for s in sess_items
                ]

                # Always expand into detailed subtopics and distribute across sessions.
                # (Schedule model may output broad topics; we want fine-grained subtopics for the drawer.)
                try:
                    plan = generate_topics_plan(
                        student_form=student_form,
                        subject=subject,
                        scope=scope,
                        session_count=session_count,
                        session_schedule=session_schedule,
                        client=current_app.config.get("GEMINI_CLIENT"),
                        types=current_app.config.get("GEMINI_TYPES"),
                        model_name=current_app.config.get("GEMINI_MODEL_NAME"),
                    )
                except Exception:
                    plan = {"all_topics": [], "sessions": []}

                all_topics = [str(x).strip() for x in (plan.get("all_topics") or []) if str(x).strip()]
                sessions_plan = list(plan.get("sessions") or [])
                topics_by_index: dict[int, list[str]] = {}
                for sp in sessions_plan:
                    try:
                        idx = int(sp.get("index") or 0)
                    except Exception:
                        idx = 0
                    if idx <= 0:
                        continue
                    topics_by_index[idx] = [str(x).strip() for x in (sp.get("topics") or []) if str(x).strip()]

                for idx, s in enumerate(sess_items, start=1):
                    sid = int(s.get("id") or 0)
                    if sid <= 0:
                        continue

                    # Compute duration.
                    dur = None
                    try:
                        st = str(s.get("start_time") or "")
                        et = str(s.get("end_time") or "")
                        sh, sm = st.split(":")
                        eh, em = et.split(":")
                        dur = max(15, (int(eh) * 60 + int(em)) - (int(sh) * 60 + int(sm)))
                    except Exception:
                        dur = None

                    # Rename schedule item for clarity: "Phy - Study 1"
                    new_subject = f"{subject} - Study {idx}" if idx > 0 else f"{subject} - Study"
                    try:
                        web_db.update_schedule_item(user_id=int(user["id"]), schedule_item_id=sid, patch={"subject": new_subject})
                    except Exception:
                        pass

                    # Persist topics per session for instant UI (never skip).
                    topics_for_session = topics_by_index.get(idx, [])
                    if not topics_for_session:
                        # Fallback: use the assignment scope split as a minimal list.
                        topics_for_session = [scope] if scope else [subject]

                    try:
                        web_db.upsert_revision_session(
                            user_id=int(user["id"]),
                            schedule_item_id=sid,
                            assignment_id=aid,
                            subject=new_subject,
                            scope=scope,
                            duration_minutes=dur,
                            session_count=session_count,
                            session_index=idx,
                            topics=topics_for_session,
                            all_topics=all_topics or topics_for_session,
                            study_guide_md=None,
                            chat_id=None,
                        )
                    except Exception:
                        current_app.logger.exception("Failed to persist precomputed revision topics")

            # Also handle study sessions that are not linked to a teacher assignment (task_id is null/0).
            # These still need precomputed subtopics so the drawer is instant on first click.
            sessions_by_subject: dict[str, list[dict[str, Any]]] = {}
            for it in items_for_precompute:
                try:
                    sid = int(it.get("id") or 0)
                except Exception:
                    sid = 0
                if sid <= 0:
                    continue
                tt = str(it.get("task_type") or "").strip().lower()
                if tt != "study":
                    continue
                try:
                    aid = int(it.get("task_id") or 0)
                except Exception:
                    aid = 0
                if aid > 0:
                    continue
                subj = (str(it.get("subject") or "").strip() or "Study")
                sessions_by_subject.setdefault(subj, []).append(it)

            for subj, sess_items in sessions_by_subject.items():
                sess_items.sort(
                    key=lambda x: (
                        str(x.get("date") or ""),
                        str(x.get("start_time") or ""),
                        int(x.get("id") or 0),
                    )
                )
                session_count = max(1, len(sess_items))
                # Try to extract a richer scope from the first session's reason (often contains topic list).
                scope = subj
                try:
                    r0 = str(sess_items[0].get("reason") or "")
                    # Common phrasing: "... on Topic A, Topic B." -> capture after ' on '
                    if " on " in r0:
                        cand = r0.split(" on ", 1)[1]
                        cand = cand.split(".", 1)[0].strip()
                        if cand:
                            scope = cand
                except Exception:
                    scope = subj

                session_schedule = [
                    {
                        "id": int(s.get("id") or 0),
                        "date": str(s.get("date") or ""),
                        "start_time": str(s.get("start_time") or ""),
                        "end_time": str(s.get("end_time") or ""),
                    }
                    for s in sess_items
                ]

                # Always expand into detailed subtopics and distribute across sessions.
                try:
                    plan = generate_topics_plan(
                        student_form=student_form,
                        subject=subj,
                        scope=scope,
                        session_count=session_count,
                        session_schedule=session_schedule,
                        client=current_app.config.get("GEMINI_CLIENT"),
                        types=current_app.config.get("GEMINI_TYPES"),
                        model_name=current_app.config.get("GEMINI_MODEL_NAME"),
                    )
                except Exception:
                    plan = {"all_topics": [], "sessions": []}

                all_topics = [str(x).strip() for x in (plan.get("all_topics") or []) if str(x).strip()]
                sessions_plan = list(plan.get("sessions") or [])
                topics_by_index: dict[int, list[str]] = {}
                for sp in sessions_plan:
                    try:
                        idx = int(sp.get("index") or 0)
                    except Exception:
                        idx = 0
                    if idx <= 0:
                        continue
                    topics_by_index[idx] = [str(x).strip() for x in (sp.get("topics") or []) if str(x).strip()]

                for idx, s in enumerate(sess_items, start=1):
                    sid = int(s.get("id") or 0)
                    if sid <= 0:
                        continue

                    # Compute duration.
                    dur = None
                    try:
                        st = str(s.get("start_time") or "")
                        et = str(s.get("end_time") or "")
                        sh, sm = st.split(":")
                        eh, em = et.split(":")
                        dur = max(15, (int(eh) * 60 + int(em)) - (int(sh) * 60 + int(sm)))
                    except Exception:
                        dur = None

                    # Rename schedule item for clarity.
                    new_subject = f"{subj} - Study {idx}" if idx > 0 else f"{subj} - Study"
                    try:
                        web_db.update_schedule_item(user_id=int(user["id"]), schedule_item_id=sid, patch={"subject": new_subject})
                    except Exception:
                        pass

                    topics_for_session = topics_by_index.get(idx, [])
                    if not topics_for_session:
                        topics_for_session = [scope] if scope else [subj]
                    try:
                        web_db.upsert_revision_session(
                            user_id=int(user["id"]),
                            schedule_item_id=sid,
                            assignment_id=None,
                            subject=new_subject,
                            scope=scope,
                            duration_minutes=dur,
                            session_count=session_count,
                            session_index=idx,
                            topics=topics_for_session,
                            all_topics=all_topics or topics_for_session,
                            study_guide_md=None,
                            chat_id=None,
                        )
                    except Exception:
                        current_app.logger.exception("Failed to persist precomputed revision topics (unlinked)")
        except Exception:
            current_app.logger.exception("Failed to precompute revision subtopics")

        return jsonify({"ok": True, "items": items, "assignments_count": len(assignments)})

    @app.route("/api/schedule/ai/clear", methods=["POST"])
    def api_schedule_clear_ai():
        user = web_context.role_required("student")
        deleted = web_db.clear_ai_schedule_items(user_id=int(user["id"]))

        # Make the schedule chatbot aware the user cleared the AI timetable.
        try:
            chat_id = web_schedule.get_or_create_schedule_chat_id(int(user["id"]))
            web_db.add_message(
                chat_id=chat_id,
                role="assistant",
                content=(
                    "(System) AI timetable cleared by user. "
                    "Do not assume any previously generated sessions still exist."
                ),
            )
        except Exception:
            pass

        return jsonify({"ok": True, "deleted": int(deleted)})

    @app.route("/schedule/api/schedule/study-guide", methods=["POST"])
    def get_study_guide():
        """Generate detailed study guide for a revision session."""
        user = web_context.role_required("student")
        from web_study_guide import generate_review_topics, generate_study_guide

        data = request.json or {}

        # Get parameters from request
        student_form = data.get("student_form")
        subject = data.get("subject")
        scope = data.get("scope")
        duration_minutes = data.get("duration_minutes", 120)  # default 2 hours
        topics_only = bool(data.get("topics_only"))

        assignment_id = data.get("assignment_id")
        schedule_item_id = data.get("schedule_item_id")

        # Normalize ids early.
        assignment_id_int: int | None = None
        if assignment_id is not None:
            try:
                assignment_id_int = int(assignment_id)
            except Exception:
                assignment_id_int = None

        schedule_item_id_int: int | None = None
        if schedule_item_id is not None:
            try:
                schedule_item_id_int = int(schedule_item_id)
            except Exception:
                schedule_item_id_int = None

        if not all([student_form, subject]):
            return jsonify({"error": "Missing required fields: student_form, subject"}), 400

        # Fast path for schedule drawer: cached topics only.
        if topics_only and schedule_item_id_int is not None and schedule_item_id_int > 0:
            cached = web_db.get_revision_session_for_user(user_id=int(user["id"]), schedule_item_id=schedule_item_id_int)
            if cached and cached.get("topics"):
                return jsonify(
                    {
                        "topics": cached.get("topics") or [],
                        "all_topics": cached.get("all_topics") or [],
                        "cached": True,
                    }
                )

        # If we have an assignment id, prefer pulling teacher-selected topics/scope from SQLite.
        assignment = None
        if assignment_id_int is not None:
            try:
                assignment = web_db.get_assignment(assignment_id=int(assignment_id_int))
            except Exception:
                assignment = None

        if assignment and assignment.get("scope"):
            scope = str(assignment.get("scope") or "").strip()
        elif assignment and assignment.get("description") and not scope:
            # Fallback: sometimes teacher puts topics in description.
            scope = str(assignment.get("description") or "").strip()

        if not scope:
            scope = str(subject or "").strip()

        try:
            # Convert student_form to int if it's a string
            if isinstance(student_form, str):
                student_form = int(student_form[0]) if student_form else 5

            # Compute how many revision sessions exist for this assignment before its deadline.
            session_count = 1
            session_index = 1
            session_schedule: list[dict[str, Any]] = []
            try:
                if assignment and assignment.get("deadline"):
                    deadline_iso = str(assignment.get("deadline") or "").strip()[:10]
                else:
                    deadline_iso = None

                if assignment and assignment.get("id") and deadline_iso:
                    uid = int(user["id"])
                    today_iso = datetime.utcnow().date().isoformat()
                    # Pull all schedule items up to the deadline; filter by task_id.
                    items = web_db.list_schedule_items(
                        user_id=uid,
                        start_date=today_iso,
                        end_date=deadline_iso,
                        limit=2000,
                    )
                    sessions = [
                        it
                        for it in items
                        if int(it.get("task_id") or 0) == int(assignment["id"]) and str(it.get("task_type") or "") == "study"
                    ]
                    sessions.sort(key=lambda it: (str(it.get("date") or ""), str(it.get("start_time") or ""), int(it.get("id") or 0)))
                    session_schedule = [
                        {
                            "id": int(it.get("id") or 0),
                            "date": str(it.get("date") or ""),
                            "start_time": str(it.get("start_time") or ""),
                            "end_time": str(it.get("end_time") or ""),
                        }
                        for it in sessions
                        if int(it.get("id") or 0) > 0
                    ]
                    session_count = max(1, len(session_schedule))

                    if schedule_item_id is not None:
                        try:
                            sid = int(schedule_item_id)
                            for idx, sess in enumerate(session_schedule, start=1):
                                if int(sess.get("id") or 0) == sid:
                                    session_index = idx
                                    break
                        except Exception:
                            pass
            except Exception:
                session_count = 1
                session_index = 1
                session_schedule = []

            if topics_only:
                result = generate_review_topics(
                    student_form=student_form,
                    subject=subject,
                    scope=scope,
                    duration_minutes=duration_minutes,
                    session_count=session_count,
                    session_index=session_index,
                    session_schedule=session_schedule,
                    client=current_app.config.get("GEMINI_CLIENT"),
                    types=current_app.config.get("GEMINI_TYPES"),
                    model_name=current_app.config.get("GEMINI_MODEL_NAME"),
                )

                if schedule_item_id_int is not None and schedule_item_id_int > 0:
                    try:
                        web_db.upsert_revision_session(
                            user_id=int(user["id"]),
                            schedule_item_id=schedule_item_id_int,
                            assignment_id=assignment_id_int,
                            subject=subject,
                            scope=scope,
                            duration_minutes=(int(duration_minutes) if duration_minutes is not None else None),
                            session_count=int(session_count),
                            session_index=int(session_index),
                            topics=list(result.get("topics") or []),
                            all_topics=list(result.get("all_topics") or []),
                            study_guide_md=None,
                            chat_id=None,
                        )
                    except Exception:
                        current_app.logger.exception("Failed to persist revision session topics")

                result = dict(result)
                result["cached"] = False
                return jsonify(result)

            # Legacy/other callers: full guide generation (not used by schedule drawer).
            result = generate_study_guide(
                student_form=student_form,
                subject=subject,
                scope=scope,
                duration_minutes=duration_minutes,
                session_count=session_count,
                session_index=session_index,
                session_schedule=session_schedule,
                client=current_app.config.get("GEMINI_CLIENT"),
                types=current_app.config.get("GEMINI_TYPES"),
                model_name=current_app.config.get("GEMINI_MODEL_NAME"),
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/schedule/availability", methods=["GET"])
    def api_get_availability():
        user = web_context.role_required("student")
        availability = web_db.get_user_availability(user_id=int(user["id"]))
        if availability:
            return jsonify(
                {
                    "ok": True,
                    "weekday_windows": availability.get("weekday_windows", []),
                    "weekend_windows": availability.get("weekend_windows", []),
                }
            )
        # Return defaults if not set
        return jsonify(
            {
                "ok": True,
                "weekday_windows": ["17:00-23:00"],
                "weekend_windows": ["07:30-23:30"],
            }
        )

    @app.route("/api/schedule/availability", methods=["POST"])
    def api_set_availability():
        user = web_context.role_required("student")
        payload: dict[str, Any] = request.get_json(silent=True) or {}
        weekday = payload.get("weekday_windows")
        weekend = payload.get("weekend_windows")

        if not isinstance(weekday, list) or not isinstance(weekend, list):
            return jsonify({"ok": False, "error": "Invalid payload, expected lists"}), 400

        # Basic validation of HH:MM-HH:MM format
        def _is_valid_window(w: str) -> bool:
            parts = w.split("-")
            return len(parts) == 2 and web_schedule.is_hhmm(parts[0].strip()) and web_schedule.is_hhmm(parts[1].strip())

        if not all(_is_valid_window(w) for w in weekday) or not all(_is_valid_window(w) for w in weekend):
            return jsonify({"ok": False, "error": "Invalid time window format (must be HH:MM-HH:MM)"}), 400

        web_db.set_user_availability(user_id=int(user["id"]), weekday_windows=weekday, weekend_windows=weekend)
        return jsonify({"ok": True})
