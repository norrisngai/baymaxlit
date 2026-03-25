"""Student schedule UI views (month/week/day)."""

from __future__ import annotations

import calendar
from datetime import date as _date
from datetime import datetime, timedelta
from typing import Any

from flask import Flask, abort, flash, redirect, render_template, request, url_for

import web_context
import web_db
import web_schedule


def register(app: Flask) -> None:
    @app.route("/schedule")
    def schedule():
        user = web_context.role_required("student")
        google_connected = bool(web_db.get_google_token(user_id=int(user["id"])))

        schedule_chat_id = web_schedule.get_or_create_schedule_chat_id(int(user["id"]))
        schedule_chat_messages = web_db.list_messages(chat_id=schedule_chat_id, limit=120)

        class_level = (user.get("class_level") or "").strip()
        if not class_level:
            flash("Missing student class.")
            return redirect(url_for("chat_home"))

        week_str = (request.args.get("week") or "").strip()
        date_str = (request.args.get("date") or "").strip()
        ym = (request.args.get("ym") or "").strip()

        today = datetime.now().date()
        today_iso = web_schedule.date_to_iso(today)
        if not ym:
            ym = today.strftime("%Y-%m")

        def to_min(t: str) -> int:
            try:
                hh, mm = t.split(":")
                return int(hh) * 60 + int(mm)
            except Exception:
                return 0

        def to_pct(mins: int) -> float:
            mins_i = max(0, min(24 * 60, int(mins)))
            return (mins_i / float(24 * 60)) * 100.0

        start_hour = 0
        end_hour = 24

        hour_lines = []
        for h in range(start_hour, end_hour):
            hour_lines.append({"top_pct": to_pct(h * 60)})

        # Only show even-hour labels (odd hours remain blank to keep spacing aligned).
        hours = []
        for h in range(start_hour, end_hour):
            hours.append(f"{h:02d}:00" if (h % 2 == 0) else "")

        # Extract student form from class_level (e.g., "5A" -> "5")
        student_form = class_level[0] if class_level else "5"

        # --- Week view ---
        if week_str:
            try:
                anchor = datetime.strptime(week_str, "%Y-%m-%d").date()
            except Exception:
                abort(400)

            week_start = anchor - timedelta(days=anchor.weekday())  # Monday
            week_end = week_start + timedelta(days=6)
            week_start_iso = web_schedule.date_to_iso(week_start)
            week_end_iso = web_schedule.date_to_iso(week_end)

            prev_week = web_schedule.date_to_iso(week_start - timedelta(days=7))
            next_week = web_schedule.date_to_iso(week_start + timedelta(days=7))

            deadlines = web_db.list_assignments_for_class_range(
                target_class=class_level,
                start_date=week_start_iso,
                end_date=week_end_iso,
                limit=400,
            )

            deadlines = web_context.filter_assignments_for_student(user=user, assignments=deadlines)

            deadlines_by_date: dict[str, list[dict[str, Any]]] = {}
            for d in deadlines:
                key = str(d.get("deadline") or "").strip()
                if not key:
                    continue
                deadlines_by_date.setdefault(key, []).append(d)

            items = web_db.list_schedule_items(
                user_id=int(user["id"]),
                start_date=week_start_iso,
                end_date=week_end_iso,
                limit=800,
            )

            rev_map = web_db.get_revision_sessions_for_user_by_schedule_ids(
                user_id=int(user["id"]),
                schedule_item_ids=[int(it.get("id") or 0) for it in items if int(it.get("id") or 0) > 0],
            )

            events_by_date: dict[str, list[dict[str, Any]]] = {}
            for it in items:
                d_iso = str(it.get("date") or "").strip()
                if not d_iso:
                    continue
                sid = int(it.get("id") or 0)
                st = str(it.get("start_time") or "00:00")
                et = str(it.get("end_time") or "00:00")
                st_min = to_min(st)
                et_min = to_min(et)
                if et_min <= st_min:
                    continue
                top_pct = to_pct(st_min)
                height_pct = max(0.1, to_pct(et_min) - to_pct(st_min))
                subject = str(it.get("subject") or "")
                task_type = str(it.get("task_type") or "study")
                task_id = it.get("task_id")
                reason = str(it.get("reason") or "")
                title = f"{subject} • {task_type}".strip(" •")

                rev = rev_map.get(sid) or {}
                detail = {
                    "task_id": int(task_id) if task_id is not None and str(task_id).isdigit() else task_id,
                    "reason": reason,
                    "topics": rev.get("topics") or [],
                    "session_index": int(rev.get("session_index") or 1) if rev else 1,
                    "session_count": int(rev.get("session_count") or 1) if rev else 1,
                    "raw": (
                        f"{d_iso}  {st}-{et}\n{title}\nTask id: {task_id if task_id is not None else ''}\nReason: {reason}"
                    ).strip(),
                }

                events_by_date.setdefault(d_iso, []).append(
                    {
                        "id": sid,
                        "date": d_iso,
                        "start_time": st,
                        "end_time": et,
                        "subject": subject,
                        "task_type": task_type,
                        "reason": reason,
                        "top_pct": float(top_pct),
                        "height_pct": float(height_pct),
                        "title": title,
                        "time": f"{st}-{et}",
                        "detail": detail,
                    }
                )

            week_cols = []
            for i in range(7):
                d = week_start + timedelta(days=i)
                d_iso = web_schedule.date_to_iso(d)
                week_cols.append(
                    {
                        "date": d_iso,
                        "label": d.strftime("%a"),
                        "day": d.strftime("%d"),
                        "events": events_by_date.get(d_iso, []),
                        "deadlines": deadlines_by_date.get(d_iso, []),
                    }
                )

            week_label = f"{week_start_iso} — {week_end_iso}"

            # Week view must fit 00:00–24:00 on screen (no scrolling in the timetable).
            # Labels are shown up to 22:00 (no "24:00" label).
            week_hours = []
            for h in range(0, 24):
                week_hours.append(f"{h:02d}:00" if (h % 2 == 0 and h <= 22) else "")

            return render_template(
                "schedule.html",
                view="week",
                ym=ym,
                today_iso=today_iso,
                next_week=next_week,
                prev_week=prev_week,
                google_connected=google_connected,
                schedule_chat_id=schedule_chat_id,
                schedule_chat_messages=schedule_chat_messages,
                week_label=week_label,
                week_anchor=week_str,
                deadlines=deadlines,
                week_cols=week_cols,
                hours=hours,
                week_hours=week_hours,
                hour_lines=hour_lines,
                timeline_height=None,
                student_form=student_form,
            )

        # --- Day view ---
        if date_str:
            deadlines = web_db.list_assignments_for_class_range(
                target_class=class_level,
                start_date=date_str,
                end_date=date_str,
                limit=200,
            )

            deadlines = web_context.filter_assignments_for_student(user=user, assignments=deadlines)

            items = web_db.list_schedule_items(
                user_id=int(user["id"]),
                start_date=date_str,
                end_date=date_str,
                limit=200,
            )

            rev_map = web_db.get_revision_sessions_for_user_by_schedule_ids(
                user_id=int(user["id"]),
                schedule_item_ids=[int(it.get("id") or 0) for it in items if int(it.get("id") or 0) > 0],
            )

            events = []
            for it in items:
                sid = int(it.get("id") or 0)
                st = str(it.get("start_time") or "00:00")
                et = str(it.get("end_time") or "00:00")
                st_min = to_min(st)
                et_min = to_min(et)
                if et_min <= st_min:
                    continue
                top_pct = to_pct(st_min)
                height_pct = max(0.1, to_pct(et_min) - to_pct(st_min))
                subject = str(it.get("subject") or "")
                task_type = str(it.get("task_type") or "study")
                task_id = it.get("task_id")
                reason = str(it.get("reason") or "")
                title = f"{subject} • {task_type}".strip(" •")

                rev = rev_map.get(sid) or {}
                detail = {
                    "task_id": int(task_id) if task_id is not None and str(task_id).isdigit() else task_id,
                    "reason": reason,
                    "topics": rev.get("topics") or [],
                    "session_index": int(rev.get("session_index") or 1) if rev else 1,
                    "session_count": int(rev.get("session_count") or 1) if rev else 1,
                    "raw": (
                        f"{date_str}  {st}-{et}\n{title}\nTask id: {task_id if task_id is not None else ''}\nReason: {reason}"
                    ).strip(),
                }
                events.append(
                    {
                        "id": sid,
                        "date": date_str,
                        "start_time": st,
                        "end_time": et,
                        "subject": subject,
                        "task_type": task_type,
                        "reason": reason,
                        "top_pct": float(top_pct),
                        "height_pct": float(height_pct),
                        "title": title,
                        "time": f"{st}-{et}",
                        "detail": detail,
                    }
                )

            return render_template(
                "schedule.html",
                view="day",
                date=date_str,
                ym=ym,
                today_iso=today_iso,
                google_connected=google_connected,
                schedule_chat_id=schedule_chat_id,
                schedule_chat_messages=schedule_chat_messages,
                deadlines=deadlines,
                events=events,
                hours=hours,
                hour_lines=hour_lines,
                timeline_height=None,
                student_form=student_form,
            )

        # --- Month view ---
        try:
            year, month = ym.split("-")
            year_i = int(year)
            month_i = int(month)
            first = _date(year_i, month_i, 1)
        except Exception:
            abort(400)

        last_day = calendar.monthrange(first.year, first.month)[1]
        last = _date(first.year, first.month, last_day)

        deadlines = web_db.list_assignments_for_class_range(
            target_class=class_level,
            start_date=first.strftime("%Y-%m-%d"),
            end_date=last.strftime("%Y-%m-%d"),
            limit=500,
        )

        deadlines = web_context.filter_assignments_for_student(user=user, assignments=deadlines)
        deadlines_by_date: dict[str, list[dict[str, Any]]] = {}
        for d in deadlines:
            key = str(d.get("deadline") or "")
            deadlines_by_date.setdefault(key, []).append(d)

        # Also show student's planned schedule items inside month boxes.
        plan_items = web_db.list_schedule_items(
            user_id=int(user["id"]),
            start_date=first.strftime("%Y-%m-%d"),
            end_date=last.strftime("%Y-%m-%d"),
            limit=800,
        )
        plans_by_date: dict[str, list[dict[str, Any]]] = {}
        for it in plan_items:
            key = str(it.get("date") or "")
            plans_by_date.setdefault(key, []).append(it)

        # Build a 6-week grid starting Monday.
        start_weekday = first.weekday()  # Monday=0
        grid_start = first - timedelta(days=start_weekday)
        month_cells = []
        today = datetime.now().date()
        for i in range(42):
            day = grid_start + timedelta(days=i)
            day_iso = day.strftime("%Y-%m-%d")
            in_month = day.month == first.month
            is_past = day < today

            d_all = deadlines_by_date.get(day_iso, [])
            p_all = plans_by_date.get(day_iso, [])

            # Month cell UI: show only the first 2 items total, then a "+n" indicator.
            rows_all: list[dict[str, Any]] = []
            for d in d_all:
                subj = str(d.get("subject") or "").strip()
                typ = str(d.get("item_type") or "").strip()
                text = f"{subj} • {typ}".strip(" •")
                if text:
                    rows_all.append({"kind": "deadline", "text": text})
            for p in p_all:
                subj = str(p.get("subject") or "").strip()
                st = str(p.get("start_time") or "").strip()
                et = str(p.get("end_time") or "").strip()
                pid = int(p.get("id") or 0) or None
                text = subj
                if st and et:
                    text = f"{subj} ({st}-{et})".strip()
                if text:
                    rows_all.append({"kind": "plan", "id": pid, "text": text})

            rows = rows_all[:2]
            more_count = max(0, len(rows_all) - len(rows))
            month_cells.append(
                {
                    "date": day_iso,
                    "day": day.day,
                    "in_month": in_month,
                    "past": is_past,
                    # Legacy fields (still used elsewhere):
                    "deadlines": d_all[:2],
                    "plans": p_all[:2],
                    # New unified list used by the month grid:
                    "rows": rows,
                    "more_count": more_count,
                }
            )

        prev_month = (first.replace(day=1) - timedelta(days=1)).replace(day=1)
        next_month = (last + timedelta(days=1)).replace(day=1)

        month_label = first.strftime("%Y %B")
        week_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        return render_template(
            "schedule.html",
            view="month",
            ym=ym,
            today_iso=today_iso,
            month_label=month_label,
            prev_ym=prev_month.strftime("%Y-%m"),
            next_ym=next_month.strftime("%Y-%m"),
            week_days=week_days,
            month_cells=month_cells,
            google_connected=google_connected,
            student_form=student_form,
            schedule_chat_id=schedule_chat_id,
            schedule_chat_messages=schedule_chat_messages,
        )
