"""Schedule/date/scheduling-chat helpers extracted from web_app.py.

These functions are called by web_app.py and must preserve behavior.
"""

from __future__ import annotations

import calendar
import math
import json
import re
from datetime import date as _date
from datetime import datetime, timedelta
from typing import Any, Optional

from flask import session

import web_context
import web_db
import web_schedule_prompt

try:
    from dateutil import parser as date_parser  # type: ignore
except Exception:  # pragma: no cover
    date_parser = None


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction (array or object) from model output."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty model output")

    # Fast path: exact JSON.
    try:
        return json.loads(raw)
    except Exception:
        pass

    # Robust path: find and decode the first JSON value, ignoring any trailing text.
    # This handles common model outputs like:
    #   [ ... ]\n\n(extra commentary)
    # which would otherwise raise: "Extra data".
    decoder = json.JSONDecoder()
    start = None
    for i, ch in enumerate(raw):
        if ch in "[{":
            start = i
            break
    if start is None:
        raise ValueError("No JSON found")

    # Try decoding from the first bracket; if it fails, scan forward for the next one.
    for i in range(start, len(raw)):
        if raw[i] not in "[{":
            continue
        try:
            obj, _end = decoder.raw_decode(raw[i:])
            return obj
        except Exception:
            continue

    # Last resort: regex capture (kept for compatibility).
    m = re.search(r"(\[.*\]|\{.*\})", raw, flags=re.DOTALL)
    if not m:
        raise ValueError("No JSON found")
    return json.loads(m.group(1))


def is_iso_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except Exception:
        return False

#It checks whether a string represents a valid time in 24-hour HH:MM format (hours and minutes)
def is_hhmm(value: str) -> bool:
    if not re.fullmatch(r"\d{2}:\d{2}", value or ""):
        return False
    try:
        hh, mm = value.split(":")
        h = int(hh)
        m = int(mm)
        return 0 <= h <= 23 and 0 <= m <= 59
    except Exception:
        return False


def normalize_date_any(value: str) -> str:
    """Normalize a date string to YYYY-MM-DD.

    Accepts many human formats (e.g. 22-jan, 22/1, Jan 22, 2026-01-22).
    """
    v = (value or "").strip()
    if not v:
        return ""
    if is_iso_date(v):
        return v
    if not date_parser:
        return ""
    try:
        # dayfirst=True to support common HK/UK formats like 22/1.
        dt = date_parser.parse(v, dayfirst=True, fuzzy=True, default=datetime.now())
        return dt.date().isoformat()
    except Exception:
        return ""


def normalize_time_any(value: str) -> str:
    """Normalize a time string to HH:MM (24h). Accepts 8pm, 20:00, 8:30 pm, etc."""
    v = (value or "").strip()
    if not v:
        return ""
    if is_hhmm(v):
        return v
    if not date_parser:
        return ""
    try:
        dt = date_parser.parse(v, fuzzy=True, default=datetime(2000, 1, 1, 0, 0))
        return f"{dt.hour:02d}:{dt.minute:02d}"
    except Exception:
        return ""


def get_or_create_schedule_chat_id(user_id: int) -> int:
    cid = session.get("schedule_chat_id")
    if cid:
        chat = web_db.get_chat(chat_id=int(cid), user_id=int(user_id))
        if chat and chat.get("chat_type") == "schedule":
            return int(cid)
    new_id = web_db.create_chat(user_id=int(user_id), title="Schedule", chat_type="schedule")
    session["schedule_chat_id"] = int(new_id)
    return int(new_id)


def schedule_edit_reply(
    *,
    user: dict[str, Any],
    chat_id: int,
    user_text: str,
    client: Any,
    types: Any,
    model_name: str,
) -> tuple[str, bool]:
    """Chat endpoint specialized for editing schedule items.

    Returns (reply_text, changed_schedule).
    """
    # Always store the user message.
    web_db.add_message(chat_id=chat_id, role="user", content=user_text)

    if not client or not types:
        reply = "Schedule editing requires Gemini configured."
        web_db.add_message(chat_id=chat_id, role="assistant", content=reply)
        return reply, False

    uid = int(user["id"])
    class_level = (user.get("class_level") or "").strip()
    if class_level:
        upcoming = web_db.get_upcoming_assignments_for_class(target_class=class_level, limit=50)
    else:
        upcoming = []

    upcoming = web_context.filter_assignments_for_student(user=user, assignments=upcoming)
    now_dt = datetime.now()
    today_iso = now_dt.date().isoformat()
    current_ym = now_dt.strftime("%Y-%m")
    existing_items = web_db.list_schedule_items(user_id=uid, start_date=today_iso, end_date=None, limit=200)

    # Include recent schedule-chat history so the model can resolve multi-turn details
    # (e.g. user gives date in one message, time in another).
    recent_msgs = web_db.list_messages(chat_id=chat_id, limit=40)
    recent_msgs = recent_msgs[-30:]

    system = (
        "You are a scheduling assistant that edits a student's calendar. "
        "Students are allowed to add ANY planning (meetings, studying, chores, personal events, meeting with friends, family, tutors, etc.). \n"
        "You MUST output ONLY valid JSON.\n\n"
        "Return a JSON object with:\n"
        "- reply: short message to the student\n"
        "- ops: array of operations to apply\n\n"
        "Operation schema:\n"
        "- {op: 'add', item: {date, start_time, end_time, subject, task_type, task_id, reason}}\n"
        "- {op: 'update', id: <schedule_item_id>, patch: {date?, start_time?, end_time?, subject?, task_type?, task_id?, reason?}}\n"
        "- {op: 'delete', id: <schedule_item_id>}\n\n"
        "Rules:\n"
        "- Only edit items that belong to this student (use provided ids).\n"
        "- Use ISO date YYYY-MM-DD and 24h time HH:MM.\n"
        "- Accept many user date/time formats (e.g. '22-jan', '22/1', '8pm', '20:00', 'this month 22'). Convert them to ISO in your ops.\n"
        "- If the request is ambiguous, ask a question in reply and return ops: [].\n"
        "- Keep schedule realistic; avoid overlaps.\n"
        "- As soon as you have: date, start_time, end_time, and subject (what to do), output an add op immediately.\n"
    )

    context = {
        "today": today_iso,
        "current_month": current_ym,
        "student": {"name": user.get("name"), "class_level": class_level},
        "recent_chat": [{"role": m.get("role"), "content": m.get("content")} for m in recent_msgs],
        "upcoming_deadlines": [
            {
                "id": a.get("id"),
                "task_type": a.get("item_type"),
                "subject": a.get("subject"),
                "deadline": a.get("deadline"),
                "description": a.get("description"),
            }
            for a in upcoming
        ],
        "existing_schedule_items": [
            {
                "id": it.get("id"),
                "date": it.get("date"),
                "start_time": it.get("start_time"),
                "end_time": it.get("end_time"),
                "subject": it.get("subject"),
                "task_type": it.get("task_type"),
                "task_id": it.get("task_id"),
                "reason": it.get("reason"),
            }
            for it in existing_items
        ],
        "user_request": user_text,
    }

    try:
        resp = client.models.generate_content(
            model=model_name,
            contents=[types.Content(role="user", parts=[types.Part(text=json.dumps(context, ensure_ascii=False))])],
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.2,
                max_output_tokens=2048,
            ),
        )
        raw = (resp.text or "").strip()
        data = extract_json(raw)
    except Exception:
        reply = "I couldn't understand that yet. Please tell me the date, start time, end time, and what you want to do."
        web_db.add_message(chat_id=chat_id, role="assistant", content=reply)
        return reply, False
    if not isinstance(data, dict):
        raise ValueError("Model output must be a JSON object")

    reply = str(data.get("reply") or "")
    ops = data.get("ops")
    if not isinstance(ops, list):
        ops = []

    changed = False
    for op in ops:
        if not isinstance(op, dict):
            continue
        kind = (op.get("op") or "").strip().lower()
        if kind == "add":
            item = op.get("item")
            if not isinstance(item, dict):
                continue
            d = normalize_date_any(str(item.get("date") or ""))
            st = normalize_time_any(str(item.get("start_time") or ""))
            et = normalize_time_any(str(item.get("end_time") or ""))
            subj = str(item.get("subject") or "").strip()
            ttype = str(item.get("task_type") or "study")
            tid = item.get("task_id")
            reason = str(item.get("reason") or "").strip() or "Planned via chat"

            if not (is_iso_date(d) and is_hhmm(st) and is_hhmm(et) and subj):
                continue
            task_id = int(tid) if tid is not None and str(tid).isdigit() else None
            web_db.add_schedule_item(
                user_id=uid,
                date=d,
                start_time=st,
                end_time=et,
                subject=subj,
                task_type=ttype,
                task_id=task_id,
                reason=reason,
            )
            changed = True

        elif kind == "update":
            sid = op.get("id")
            patch = op.get("patch")
            if sid is None or not isinstance(patch, dict):
                continue
            try:
                sid_i = int(sid)
            except Exception:
                continue

            # Normalize + validate patch fields if present.
            if "date" in patch:
                patch["date"] = normalize_date_any(str(patch.get("date") or ""))
                if not is_iso_date(str(patch.get("date") or "")):
                    continue
            if "start_time" in patch:
                patch["start_time"] = normalize_time_any(str(patch.get("start_time") or ""))
                if not is_hhmm(str(patch.get("start_time") or "")):
                    continue
            if "end_time" in patch:
                patch["end_time"] = normalize_time_any(str(patch.get("end_time") or ""))
                if not is_hhmm(str(patch.get("end_time") or "")):
                    continue
            if "reason" in patch and not str(patch.get("reason") or "").strip():
                patch["reason"] = "Planned via chat"

            ok = web_db.update_schedule_item(user_id=uid, schedule_item_id=sid_i, patch=patch)
            changed = changed or ok

        elif kind == "delete":
            sid = op.get("id")
            try:
                sid_i = int(sid)
            except Exception:
                continue
            ok = web_db.delete_schedule_item(user_id=uid, schedule_item_id=sid_i)
            changed = changed or ok

    if not reply:
        reply = "Done."

    web_db.add_message(chat_id=chat_id, role="assistant", content=reply)
    return reply, changed


def date_to_iso(d: _date) -> str:
    return d.strftime("%Y-%m-%d")


def heuristic_schedule(*, assignments: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    """Fallback planner when Gemini is unavailable."""
    now = datetime.now()
    start_day = now.date()
    end_day = start_day + timedelta(days=max(0, int(days) - 1))

    def _to_min(t: str) -> int:
        try:
            hh, mm = t.split(":")
            return int(hh) * 60 + int(mm)
        except Exception:
            return -1

    def _to_hhmm(m: int) -> str:
        h = max(0, m) // 60
        mm = max(0, m) % 60
        return f"{h:02d}:{mm:02d}"

    def _allowed_range(d: _date) -> tuple[int, int]:
        wd = d.weekday()  # Mon=0 ... Sun=6
        if wd >= 5:
            return _to_min("07:30"), _to_min("23:30")
        return _to_min("17:00"), _to_min("23:00")

    def type_weight(t: str) -> int:
        t = (t or "").lower()
        if t == "exam":
            return 4
        if t == "test":
            return 3
        if t == "quiz":
            return 2
        return 1

    norm = []
    for a in assignments:
        try:
            dl = datetime.strptime(str(a.get("deadline") or ""), "%Y-%m-%d").date()
        except Exception:
            continue
        if dl < start_day:
            continue
        urgency_days = max(0, (dl - start_day).days)
        norm.append((urgency_days, -type_weight(str(a.get("item_type") or "homework")), a, dl))

    norm.sort(key=lambda x: (x[0], x[1]))

    # We avoid hard-coded specific time slots. Instead, place sessions sequentially
    # within the allowed weekday/weekend windows.
    per_day_next_start: dict[str, int] = {}
    items: list[dict[str, Any]] = []

    for _, __, a, dl in norm:
        # Allocate 1 session; if it's an exam/test, allocate 2 sessions if possible.
        needed = 2 if str(a.get("item_type") or "").lower() in {"exam", "test"} else 1
        for k in range(needed):
            placed = False
            # schedule earlier days first, leaving buffer (avoid last day if possible)
            last_allowed = min(end_day, max(start_day, dl - timedelta(days=1)))
            for offset in range((last_allowed - start_day).days + 1):
                d = start_day + timedelta(days=offset)
                d_iso = date_to_iso(d)
                min_start, max_end = _allowed_range(d)
                next_start = per_day_next_start.get(d_iso, min_start)
                # Session length: 2 hours, with 30 minutes buffer/break after.
                session_len = 120
                buffer_len = 30
                st_min = next_start
                et_min = st_min + session_len
                if et_min > max_end:
                    continue
                st, et = _to_hhmm(st_min), _to_hhmm(et_min)
                per_day_next_start[d_iso] = et_min + buffer_len
                items.append(
                    {
                        "date": d_iso,
                        "start_time": st,
                        "end_time": et,
                        "subject": a.get("subject") or "(unknown)",
                        "task_type": a.get("item_type") or "homework",
                        "task_id": a.get("id"),
                        "reason": f"Planned session {k+1}/{needed} before {dl.isoformat()} deadline.",
                    }
                )
                placed = True
                break
            if not placed:
                # If no slot found, skip.
                break

    return items


def heuristic_schedule_in_free_windows(
    *,
    assignments: list[dict[str, Any]],
    window_dates: list[_date],
    free_by_date: dict[str, list[tuple[int, int]]],
) -> list[dict[str, Any]]:
    """Heuristic fallback that *directly* schedules into free windows.

    This is used when Gemini is not configured. It avoids the situation where a
    naive heuristic schedules inside the base window but conflicts with fixed
    events, causing validation to drop everything.
    """

    if not window_dates:
        return []

    start_day = window_dates[0]
    end_day = window_dates[-1]

    def _to_min(t: str) -> int:
        try:
            hh, mm = t.split(":")
            return int(hh) * 60 + int(mm)
        except Exception:
            return -1

    def _to_hhmm(m: int) -> str:
        m2 = max(0, min(24 * 60, int(m)))
        return f"{m2 // 60:02d}:{m2 % 60:02d}"

    def type_weight(t: str) -> int:
        t2 = (t or "").strip().lower()
        if t2 in {"exam"}:
            return 5
        if t2 in {"test"}:
            return 4
        if t2 in {"quiz"}:
            return 3
        return 1

    def estimate_hours(task_type: str) -> float:
        t = (task_type or "").strip().lower()
        if t in {"exam", "test"}:
            return 36.0
        if t == "quiz":
            return 3.0
        return 2.0

    # Normalize & prioritize assignments
    norm: list[tuple[int, int, dict[str, Any], _date]] = []
    for a in assignments or []:
        try:
            dl = datetime.strptime(str(a.get("deadline") or ""), "%Y-%m-%d").date()
        except Exception:
            continue
        if dl < start_day:
            continue
        urgency_days = max(0, (dl - start_day).days)
        norm.append((urgency_days, -type_weight(str(a.get("item_type") or a.get("task_type") or "homework")), a, dl))
    norm.sort()

    # Cursor per date for where to place next session.
    per_day_cursor: dict[str, int] = {}
    per_day_window_index: dict[str, int] = {}

    def _next_slot(date_iso: str, duration_min: int, buffer_min: int) -> Optional[tuple[int, int]]:
        windows = free_by_date.get(date_iso, [])
        if not windows:
            return None
        idx = per_day_window_index.get(date_iso, 0)
        cur = per_day_cursor.get(date_iso, windows[0][0])

        while idx < len(windows):
            ws, we = windows[idx]
            cur = max(cur, ws)
            if cur + duration_min <= we:
                st = cur
                et = cur + duration_min
                per_day_cursor[date_iso] = et + buffer_min
                per_day_window_index[date_iso] = idx
                return (st, et)

            idx += 1
            if idx < len(windows):
                cur = windows[idx][0]

        per_day_cursor[date_iso] = cur
        per_day_window_index[date_iso] = idx
        return None

    items: list[dict[str, Any]] = []

    for urgency_days, _w, a, dl in norm:
        try:
            task_id = int(a.get("id") or 0)
        except Exception:
            task_id = 0
        subject = str(a.get("subject") or "(unknown)")
        task_type = str(a.get("item_type") or a.get("task_type") or "homework").strip().lower() or "homework"

        hours = estimate_hours(task_type)
        needed = max(1, int(math.ceil(hours / 2.0)))
        needed = min(needed, 6)

        last_allowed = min(end_day, max(start_day, dl - timedelta(days=1)))
        last_offset = (last_allowed - start_day).days

        for k in range(needed):
            placed = False
            for offset in range(last_offset + 1):
                d = start_day + timedelta(days=offset)
                d_iso = date_to_iso(d)
                slot = _next_slot(d_iso, 120, 30)
                if not slot:
                    continue
                sm, em = slot
                items.append(
                    {
                        "date": d_iso,
                        "start_time": _to_hhmm(sm),
                        "end_time": _to_hhmm(em),
                        "subject": subject,
                        "task_type": task_type,
                        "task_id": task_id if task_id > 0 else None,
                        "reason": f"Planned session {k+1}/{needed} before {dl.isoformat()} deadline.",
                    }
                )
                placed = True
                break
            if not placed:
                break

    return items


def generate_schedule_items(
    *,
    user: dict[str, Any],
    assignments: list[dict[str, Any]],
    days: int,
    client: Any,
    types: Any,
    model_name: str,
) -> list[dict[str, Any]]:
    """Generate a student's timetable using AI.

    - Gets tasks and existing schedule from the database.
    - Calls the model with structured JSON input.
    - The model is responsible for all scheduling logic.
    - Returns the generated schedule items.
    """
    uid = int(user.get("id") or 0)
    if uid <= 0:
        raise ValueError("Missing user id")

    if not client or not types:
        raise ValueError("AI client is not configured.")

    today = datetime.now().date()
    start_date = today.isoformat()
    end_date = (today + timedelta(days=days)).isoformat()

    # Load student availability (weekday/weekend windows) from DB.
    availability = web_db.get_user_availability(user_id=uid) or {}
    weekday_windows = availability.get("weekday_windows") or ["17:00-23:00"]
    weekend_windows = availability.get("weekend_windows") or ["07:30-23:30"]

    # Build per-date free windows based on availability. This is authoritative for scheduling.
    def _windows_for_date(d: _date) -> list[str]:
        return list(weekend_windows if d.weekday() >= 5 else weekday_windows)

    free_windows_by_date: dict[str, list[str]] = {}
    for i in range(max(0, int(days)) + 1):
        d = today + timedelta(days=i)
        free_windows_by_date[d.isoformat()] = _windows_for_date(d)

    def _to_min(t: str) -> int:
        try:
            hh, mm = (t or "").strip().split(":")
            return int(hh) * 60 + int(mm)
        except Exception:
            return -1

    def _windows_min(date_iso: str) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for w in free_windows_by_date.get(date_iso, []) or []:
            parts = str(w or "").strip().split("-")
            if len(parts) != 2:
                continue
            a = _to_min(parts[0])
            b = _to_min(parts[1])
            if a < 0 or b < 0 or b <= a:
                continue
            out.append((a, b))
        return out

    def _within_windows(*, date_iso: str, start_hhmm: str, end_hhmm: str) -> bool:
        st = _to_min(start_hhmm)
        et = _to_min(end_hhmm)
        if st < 0 or et < 0 or et <= st:
            return False
        for ws, we in _windows_min(date_iso):
            if st >= ws and et <= we:
                return True
        return False

    # Get existing schedule items to provide to the AI
    existing_items = web_db.list_schedule_items(user_id=uid, start_date=start_date, end_date=end_date)

    # Prepare the input for the AI
    def _norm_task(a: dict[str, Any]) -> dict[str, Any]:
        # Convert incoming assignment dict (SQLite) to a stable schema for the model.
        subj = str(a.get("subject") or "").strip()
        item_type = str(a.get("item_type") or a.get("task_type") or "").strip().lower()
        deadline = str(a.get("deadline") or "").strip()
        scope = str(a.get("scope") or "").strip()
        desc = str(a.get("description") or "").strip()
        try:
            task_id = int(a.get("id") or a.get("task_id") or 0) or None
        except Exception:
            task_id = None
        return {
            "task_id": task_id,
            "subject": subj,
            "task_type": item_type,
            "scope": scope,
            "description": desc,
            "deadline": deadline,
        }

    ai_input = {
        "student": {"id": uid, "name": user.get("name"), "class_level": user.get("class_level")},
        "availability": {
            "weekday_windows": list(weekday_windows),
            "weekend_windows": list(weekend_windows),
        },
        "date_window": {"start": start_date, "end": end_date},
        "free_windows_by_date": free_windows_by_date,
        "tasks": [_norm_task(a) for a in (assignments or []) if isinstance(a, dict)],
        "existing_schedule": existing_items,
    }

    system_prompt = web_schedule_prompt.schedule_system_prompt()
    user_prompt = json.dumps(ai_input, ensure_ascii=False)

    try:
        resp = client.models.generate_content(
            model=model_name,
            contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,
                max_output_tokens=8192,
                response_mime_type="application/json",
            ),
        )
        raw_json = (resp.text or "").strip()
        generated_items = json.loads(raw_json)

        if isinstance(generated_items, dict):
            # Handle cases where the model returns {"schedule": [...]}
            for key in ("schedule", "items", "plan"):
                if isinstance(generated_items.get(key), list):
                    generated_items = generated_items[key]
                    break
        
        if not isinstance(generated_items, list):
            raise ValueError("AI response is not a list of schedule items.")

        def _norm_task_type(v: Any) -> str:
            t = str(v or "").strip().lower()
            # Legacy model outputs sometimes say "revision".
            if t == "revision":
                return "study"
            # Keep only DB-supported types.
            if t not in {"homework", "quiz", "test", "exam", "study", "activity"}:
                # Default unknown planning to study.
                return "study"
            return t

        # Build per-subject assignment candidates for linking.
        assignments_by_subject: dict[str, list[dict[str, Any]]] = {}
        for a in assignments or []:
            if not isinstance(a, dict):
                continue
            subj = str(a.get("subject") or "").strip()
            if not subj:
                continue
            assignments_by_subject.setdefault(subj.lower(), []).append(a)

        def _infer_task_id(*, subject: str, task_type: str, date_iso: str) -> int | None:
            subj_key = (subject or "").strip().lower()
            if not subj_key:
                return None
            cand = assignments_by_subject.get(subj_key) or []
            if not cand:
                return None

            # Parse date to compare against deadlines.
            try:
                d = datetime.strptime(date_iso, "%Y-%m-%d").date()
            except Exception:
                d = None

            # Prefer matching by task type.
            want_types: set[str]
            if task_type in {"homework", "quiz", "test", "exam"}:
                want_types = {task_type}
            else:
                # Study sessions should map to assessments (quiz/test/exam) when possible.
                want_types = {"quiz", "test", "exam"}

            scored: list[tuple[int, dict[str, Any]]] = []
            for a in cand:
                try:
                    aid = int(a.get("id") or 0)
                except Exception:
                    continue
                if aid <= 0:
                    continue
                at = str(a.get("item_type") or a.get("task_type") or "").strip().lower()
                if at and at not in want_types:
                    continue
                dl_raw = str(a.get("deadline") or "").strip()[:10]
                if not dl_raw:
                    continue
                try:
                    dl = datetime.strptime(dl_raw, "%Y-%m-%d").date()
                except Exception:
                    continue
                if d and d >= dl:
                    continue
                # Score by how close the deadline is (smaller is better).
                delta = (dl - d).days if d else 9999
                scored.append((max(0, int(delta)), a))
            if not scored:
                return None
            scored.sort(key=lambda x: x[0])
            try:
                return int(scored[0][1].get("id") or 0) or None
            except Exception:
                return None

        # Normalize and enrich generated items.
        cleaned: list[dict[str, Any]] = []
        for item in generated_items:
            if not isinstance(item, dict):
                continue
            d = str(item.get("date") or "").strip()
            st = str(item.get("start_time") or "").strip()
            et = str(item.get("end_time") or "").strip()
            subject = str(item.get("subject") or "").strip() or "Study"
            task_type = _norm_task_type(item.get("task_type"))
            reason = str(item.get("reason") or "").strip() or "Planned by AI"

            raw_topics = item.get("topics")
            topics_list: list[str] = []
            if isinstance(raw_topics, list):
                topics_list = [str(x).strip() for x in raw_topics if str(x).strip()]

            task_id_val = item.get("task_id")
            task_id_int: int | None
            try:
                task_id_int = int(task_id_val) if task_id_val is not None and str(task_id_val).strip() != "" else None
            except Exception:
                task_id_int = None

            # Infer task_id when missing and it looks like it ties to a provided task.
            if task_id_int is None:
                inferred = _infer_task_id(subject=subject, task_type=task_type, date_iso=d)
                if inferred:
                    task_id_int = inferred

            out = {
                "date": d,
                "start_time": st,
                "end_time": et,
                "subject": subject,
                "task_type": task_type,
                "task_id": task_id_int,
                "reason": reason,
            }
            if task_type == "study" and topics_list:
                out["topics"] = topics_list

            # Enforce availability windows: discard anything outside the student's allowed times.
            if _within_windows(date_iso=d, start_hhmm=st, end_hhmm=et):
                cleaned.append(out)

        generated_items = cleaned

        return generated_items

    except Exception as e:
        print(f"Error generating schedule: {e}")
        # Fallback to an empty list if AI fails
        return []


def build_month_grid(*, ym: str) -> tuple[_date, _date, list[dict[str, Any]], str, list[str], str, str]:
    """Utility for schedule month view; kept here for reuse if needed."""
    year, month = ym.split("-")
    year_i = int(year)
    month_i = int(month)
    first = _date(year_i, month_i, 1)

    last_day = calendar.monthrange(first.year, first.month)[1]
    last = _date(first.year, first.month, last_day)

    # Build a 6-week grid starting Monday.
    start_weekday = (first.weekday())  # Monday=0
    grid_start = first - timedelta(days=start_weekday)
    month_cells = []
    for i in range(42):
        day = grid_start + timedelta(days=i)
        day_iso = day.strftime("%Y-%m-%d")
        in_month = day.month == first.month
        month_cells.append({"date": day_iso, "day": day.day, "in_month": in_month})

    prev_month = (first.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (last + timedelta(days=1)).replace(day=1)

    month_label = first.strftime("%Y %B")
    week_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    return (
        first,
        last,
        month_cells,
        month_label,
        week_days,
        prev_month.strftime("%Y-%m"),
        next_month.strftime("%Y-%m"),
    )
