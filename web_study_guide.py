"""Generate detailed study guides for revision tasks."""

from __future__ import annotations

import json
import re
import time
from typing import Any


def _extract_json(text: str) -> Any:
    """Best-effort JSON extraction (array or object) from model output."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty model output")

    try:
        return json.loads(raw)
    except Exception:
        pass

    decoder = json.JSONDecoder()
    start = None
    for i, ch in enumerate(raw):
        if ch in "[{":
            start = i
            break
    if start is None:
        raise ValueError("No JSON found")

    for i in range(start, len(raw)):
        if raw[i] not in "[{":
            continue
        try:
            obj, _end = decoder.raw_decode(raw[i:])
            return obj
        except Exception:
            continue

    m = re.search(r"(\[.*\]|\{.*\})", raw, flags=re.DOTALL)
    if not m:
        raise ValueError("No JSON found")
    return json.loads(m.group(1))


def _split_scope_to_topics(scope: str) -> list[str]:
    s = (scope or "").strip()
    if not s:
        return []

    # Normalize bullets and separators.
    s = s.replace("\r\n", "\n")
    s = s.replace("•", "-")
    s = s.replace("|", ",")

    parts: list[str] = []
    for line in s.split("\n"):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*\d.\)\]]+\s+", "", line).strip()
        if not line:
            continue
        for chunk in re.split(r"[,;]", line):
            chunk = chunk.strip()
            if chunk:
                parts.append(chunk)

    # De-dup while preserving order.
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _minutes_between(start_hhmm: str, end_hhmm: str) -> int:
    try:
        sh, sm = (start_hhmm or "").split(":")
        eh, em = (end_hhmm or "").split(":")
        return max(0, (int(eh) * 60 + int(em)) - (int(sh) * 60 + int(sm)))
    except Exception:
        return 0


def generate_study_guide(
    *,
    student_form: int,
    subject: str,
    scope: str,
    duration_minutes: int,
    session_count: int = 1,
    session_index: int = 1,
    session_schedule: list[dict[str, Any]] | None = None,
    client: Any,
    types: Any,
    model_name: str,
) -> dict[str, Any]:
    """Generate topics + a study guide for a revision session.

    Returns:
    - topics: list[str] (for current session)
    - all_topics: list[str] (all subtopics across all sessions)
    - study_guide: str (Markdown)

    Notes:
    - This function is intentionally resilient: it requests Markdown-only from Gemini
      (no JSON), and retries briefly on transient 503/429 errors.
    """

    subject = (subject or "").strip() or "General"
    duration_minutes = int(duration_minutes or 0) if int(duration_minutes or 0) > 0 else 120

    if session_count < 1:
        session_count = 1
    if session_index < 1:
        session_index = 1
    if session_index > session_count:
        session_index = session_count

    teacher_topics = _split_scope_to_topics(scope)
    if not teacher_topics:
        teacher_topics = [subject]

    seed_topics = teacher_topics

    # Determine session topics by evenly splitting.
    all_topics = seed_topics
    per = max(1, (len(all_topics) + session_count - 1) // session_count)
    start = (session_index - 1) * per
    session_topics = all_topics[start : start + per] or all_topics[: min(8, len(all_topics))]

    # Schedule metadata (optional).
    sess_list = session_schedule or []
    sess_norm: list[dict[str, Any]] = []
    for it in sess_list:
        d = str(it.get("date") or "").strip()
        st = str(it.get("start_time") or "").strip()
        et = str(it.get("end_time") or "").strip()
        sid = int(it.get("id") or 0)
        mins = _minutes_between(st, et)
        sess_norm.append({"id": sid, "date": d, "start_time": st, "end_time": et, "duration_minutes": mins})

    if not client or not types:
        study_guide = (
            "(AI unavailable) Gemini is not configured. "
            "Set GOOGLE_GEMINI_API_KEY (or local_secrets.GOOGLE_GEMINI_API_KEY) and restart the server.\n\n"
            + "Please review: "
            + ", ".join([t for t in session_topics if str(t).strip()])
        )
        return {"topics": session_topics, "all_topics": all_topics, "study_guide": study_guide}

    system = (
        "You are an expert DSE tutor.\n"
        "Output ONLY Markdown (no JSON).\n\n"
        "Math formatting (strict): write ALL math in LaTeX using \\(...\\) for inline and \\[...\\] for display. "
        "Do NOT use dollar-sign delimiters like $...$ or $$...$$.\n\n"
        "Write a detailed, time-blocked study guide with: key ideas, formulas, common traps, and short practice questions + answers.\n"
        "Use clear headings and time markers (e.g., ⏱️ 0–15 min).\n"
    )

    payload = {
        "student_form": int(student_form),
        "subject": subject,
        "duration_minutes": int(duration_minutes),
        "session_count": int(session_count),
        "session_index": int(session_index),
        "session_topics": session_topics,
        "scope_topics": teacher_topics,
        "session_schedule": sess_norm,
    }

    ai_error: Exception | None = None
    guide_md = ""
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=[types.Content(role="user", parts=[types.Part(text=json.dumps(payload, ensure_ascii=False))])],
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.3,
                    max_output_tokens=2048,
                ),
            )
            guide_md = (resp.text or "").strip()
            break
        except Exception as e:
            ai_error = e
            msg = str(e)
            is_transient = (
                "503" in msg
                or "UNAVAILABLE" in msg
                or "429" in msg
                or "RESOURCE_EXHAUSTED" in msg
                or "RATE_LIMIT" in msg
            )
            if not is_transient or attempt >= 2:
                break
            time.sleep(0.8 * (attempt + 1))

    if not guide_md:
        reason = f" (Reason: {ai_error})" if ai_error is not None else ""
        study_guide = "(AI unavailable)" + reason + " Please review: " + ", ".join(session_topics)
        return {"topics": session_topics, "all_topics": all_topics, "study_guide": study_guide}

    header_lines = [f"Topics to cover ({subject}):"]
    for t in session_topics:
        if str(t).strip():
            header_lines.append(f"- {t}")
    study_guide = "\n".join(header_lines) + "\n\n" + guide_md

    return {"topics": session_topics, "all_topics": all_topics, "study_guide": study_guide}


def generate_review_topics(
    *,
    student_form: int,
    subject: str,
    scope: str,
    duration_minutes: int,
    session_count: int = 1,
    session_index: int = 1,
    session_schedule: list[dict[str, Any]] | None = None,
    client: Any,
    types: Any,
    model_name: str,
) -> dict[str, Any]:
    """Generate only the revision subtopics (fast path for schedule drawer).

    Returns:
    - topics: string[] (for current session)
    - all_topics: string[] (all subtopics across all sessions)
    """

    subject = (subject or "").strip() or "General"
    duration_minutes = int(duration_minutes or 0) if int(duration_minutes or 0) > 0 else 120

    if session_count < 1:
        session_count = 1
    if session_index < 1:
        session_index = 1
    if session_index > session_count:
        session_index = session_count

    teacher_topics = _split_scope_to_topics(scope)
    if not teacher_topics:
        teacher_topics = [subject]

    seed_topics = teacher_topics

    # Normalize schedule metadata (not strictly required for topics-only).
    sess_list = session_schedule or []
    sess_norm: list[dict[str, Any]] = []
    for it in sess_list:
        d = str(it.get("date") or "").strip()
        st = str(it.get("start_time") or "").strip()
        et = str(it.get("end_time") or "").strip()
        sid = int(it.get("id") or 0)
        mins = _minutes_between(st, et)
        sess_norm.append({"id": sid, "date": d, "start_time": st, "end_time": et, "duration_minutes": mins})

    if not sess_norm:
        for _i in range(1, session_count + 1):
            sess_norm.append({"id": 0, "date": "", "start_time": "", "end_time": "", "duration_minutes": duration_minutes})

    # AI fast path: expand to subtopics and split across sessions.
    if client and types:
        system = (
            "You are an expert DSE revision planner.\n"
            "You MUST output ONLY valid JSON.\n\n"
            "Task: Expand the teacher-selected topics into concrete, detailed subtopics, then split them evenly across sessions.\n\n"
            "Rules:\n"
            "- Respect teacher-selected topics as the scope.\n"
            "- Produce specific subtopics (not generic like the subject name).\n"
            "- Deduplicate, keep them exam-focused.\n"
            "- Split evenly across sessions; all subtopics covered by final session.\n\n"
            "Return JSON with keys:\n"
            "- all_subtopics: string[]\n"
            "- sessions: array of {index:int, title:string, topics:string[]}\n"
        )

        payload = {
            "student_form": int(student_form),
            "subject": subject,
            "teacher_topics": teacher_topics,
            "session_count": int(session_count),
            "session_index": int(session_index),
            "session_duration_minutes": int(duration_minutes),
            "session_schedule": sess_norm,
        }

        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=[types.Content(role="user", parts=[types.Part(text=json.dumps(payload, ensure_ascii=False))])],
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.2,
                    max_output_tokens=2048,
                ),
            )
            data = _extract_json((resp.text or "").strip())
            all_subtopics = [str(x).strip() for x in (data.get("all_subtopics") or []) if str(x).strip()]
            sessions = data.get("sessions") or []
            session_topics: list[str] = []
            for s in sessions:
                try:
                    if int(s.get("index") or 0) == int(session_index):
                        session_topics = [str(x).strip() for x in (s.get("topics") or []) if str(x).strip()]
                        break
                except Exception:
                    continue
            if not session_topics:
                session_topics = all_subtopics[:10] if all_subtopics else seed_topics
            return {"topics": session_topics, "all_topics": all_subtopics}
        except Exception:
            pass

    # Deterministic fallback: split seed_topics evenly.
    all_topics = seed_topics
    per = max(1, (len(all_topics) + session_count - 1) // session_count)
    start = (session_index - 1) * per
    session_topics = all_topics[start : start + per] or all_topics[: min(10, len(all_topics))]
    return {"topics": session_topics, "all_topics": all_topics}


def generate_topics_plan(
    *,
    student_form: int,
    subject: str,
    scope: str,
    session_count: int,
    session_schedule: list[dict[str, Any]] | None,
    client: Any,
    types: Any,
    model_name: str,
) -> dict[str, Any]:
    """Generate a full per-session topics plan (fast, no study guide).

    Returns JSON-like dict:
    - all_topics: string[]
    - sessions: array of {index:int, title:string, topics:string[]}
    """

    subject = (subject or "").strip() or "General"
    if session_count < 1:
        session_count = 1

    teacher_topics = _split_scope_to_topics(scope)
    if not teacher_topics:
        teacher_topics = [subject]

    # Normalize session schedule (optional metadata for better splitting).
    sess_list = session_schedule or []
    sess_norm: list[dict[str, Any]] = []
    for it in sess_list:
        d = str(it.get("date") or "").strip()
        st = str(it.get("start_time") or "").strip()
        et = str(it.get("end_time") or "").strip()
        sid = int(it.get("id") or 0)
        mins = _minutes_between(st, et)
        sess_norm.append({"id": sid, "date": d, "start_time": st, "end_time": et, "duration_minutes": mins})
    if not sess_norm:
        for _i in range(1, session_count + 1):
            sess_norm.append({"id": 0, "date": "", "start_time": "", "end_time": "", "duration_minutes": 0})

    # AI path.
    if client and types:
        system = (
            "You are an expert DSE revision planner.\n"
            "You MUST output ONLY valid JSON.\n\n"
            "Task: Expand the teacher-selected topics into fine-grained, exam-ready subtopics and distribute them across sessions.\n\n"
            "Rules:\n"
            "- Respect teacher-selected topics as the scope.\n"
            "- Subtopics must be concrete and testable; NEVER output generic headings like 'Mechanics' or just the chapter name.\n"
            "- Each subtopic should include key details in parentheses where helpful (e.g., 'Newton's Laws (inertia, F=ma, action-reaction)').\n"
            "- Aim for 3–8 subtopics per session (roughly even).\n"
            "- Deduplicate across the whole plan.\n"
            "- Distribute evenly across sessions with minimal overlap.\n"
            "- The final session should emphasize exam-style mixed practice, common traps, and past-paper style questions based on earlier subtopics.\n\n"
            "Hard requirement:\n"
            "- You MUST return sessions for EVERY index 1..session_count (no missing sessions).\n\n"
            "Return JSON with keys:\n"
            "- all_topics: string[]\n"
            "- sessions: array of {index:int, title:string, topics:string[]}\n"
        )

        payload = {
            "student_form": int(student_form),
            "subject": subject,
            "teacher_topics": teacher_topics,
            "session_count": int(session_count),
            "session_schedule": sess_norm,
        }

        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=[types.Content(role="user", parts=[types.Part(text=json.dumps(payload, ensure_ascii=False))])],
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.2,
                    max_output_tokens=4096,
                ),
            )
            data = _extract_json((resp.text or "").strip())
            all_topics = [str(x).strip() for x in (data.get("all_topics") or []) if str(x).strip()]
            sessions_in = data.get("sessions") or []
            sessions: list[dict[str, Any]] = []
            for s in sessions_in:
                try:
                    idx = int(s.get("index") or 0)
                except Exception:
                    idx = 0
                if idx <= 0:
                    continue
                title = str(s.get("title") or f"Session {idx}").strip()
                topics = [str(x).strip() for x in (s.get("topics") or []) if str(x).strip()]
                sessions.append({"index": idx, "title": title, "topics": topics})
            sessions.sort(key=lambda x: int(x.get("index") or 0))

            # Post-process: ensure indices 1..session_count exist.
            if not all_topics:
                tmp: list[str] = []
                for s in sessions:
                    for t in (s.get("topics") or []):
                        if t and t not in tmp:
                            tmp.append(t)
                all_topics = tmp

            by_idx: dict[int, dict[str, Any]] = {}
            assigned: set[str] = set()
            for s in sessions:
                try:
                    idx = int(s.get("index") or 0)
                except Exception:
                    idx = 0
                if idx <= 0:
                    continue
                topics = [str(x).strip() for x in (s.get("topics") or []) if str(x).strip()]
                s["topics"] = topics
                by_idx[idx] = s
                for t in topics:
                    assigned.add(t)

            remaining = [t for t in all_topics if t not in assigned]
            missing = [i for i in range(1, int(session_count) + 1) if i not in by_idx]
            if missing:
                per_missing = max(3, (len(remaining) + len(missing) - 1) // len(missing))
                cursor = 0
                for i in missing:
                    chunk = remaining[cursor : cursor + per_missing]
                    cursor += per_missing
                    by_idx[i] = {"index": i, "title": f"Study {i}", "topics": chunk}
                    for t in chunk:
                        assigned.add(t)

            remaining2 = [t for t in all_topics if t not in assigned]
            cursor = 0
            for i in range(1, int(session_count) + 1):
                s = by_idx.get(i)
                if not s:
                    continue
                topics = list(s.get("topics") or [])
                if topics:
                    continue
                need = 3
                chunk = remaining2[cursor : cursor + need]
                cursor += need
                if not chunk and all_topics:
                    chunk = all_topics[: min(need, len(all_topics))]
                s["topics"] = chunk

            sessions_out = [by_idx[i] for i in range(1, int(session_count) + 1) if i in by_idx]
            return {"all_topics": all_topics, "sessions": sessions_out}
        except Exception:
            pass

    # Deterministic fallback: split seed topics evenly.
    seed_topics = teacher_topics
    per = max(1, (len(seed_topics) + session_count - 1) // session_count)
    sessions = []
    for i in range(1, session_count + 1):
        start = (i - 1) * per
        topics = seed_topics[start : start + per] or seed_topics[: min(10, len(seed_topics))]
        sessions.append({"index": i, "title": f"Study {i}", "topics": topics})
    return {"all_topics": seed_topics, "sessions": sessions}


