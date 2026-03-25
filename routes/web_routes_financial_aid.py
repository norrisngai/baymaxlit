"""Financial Aid Guidance routes.

Provides:
- /financial-aid           – list all HK scholarships / subsidies
- /financial-aid/chat      – dedicated AI chatbot for financial aid Q&A
- /api/financial-aid/chat  – AJAX endpoint for chatbot messages
"""

from __future__ import annotations

import json
import threading
from typing import Any

from flask import Flask, current_app, jsonify, redirect, render_template, request, url_for

import web_context
import web_db
import web_markdown
import web_scholarships


def register(app: Flask) -> None:

    # ------------------------------------------------------------------
    # Pre-load scholarship data in a background thread at startup
    # ------------------------------------------------------------------
    def _warmup() -> None:
        try:
            web_scholarships.get_all_scholarships()
        except Exception:
            pass

    threading.Thread(target=_warmup, daemon=True).start()

    # ------------------------------------------------------------------
    # Helper: call Gemini with financial-aid-specific system prompt
    # ------------------------------------------------------------------
    def _financial_aid_reply(*, user: dict[str, Any], chat_id: int, user_text: str) -> str:
        client = current_app.config.get("GEMINI_CLIENT")
        types = current_app.config.get("GEMINI_TYPES")
        model_name = current_app.config.get("GEMINI_MODEL_NAME")

        if not client or not types:
            return "AI is not configured. Please set GOOGLE_GEMINI_API_KEY."

        # Build conversation history
        msgs = web_db.list_messages(chat_id=chat_id, limit=50)
        contents = []
        for m in msgs:
            role = "user" if m.get("role") == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=m.get("content") or "")]))

        contents.append(types.Content(role="user", parts=[types.Part(text=user_text)]))

        # System prompt with scholarship context
        scholarship_context = ""
        try:
            scholarship_context = web_scholarships.build_scholarship_context()
        except Exception:
            scholarship_context = "(Scholarship data could not be loaded)"

        interests: list[str] = []
        try:
            interests = json.loads(user.get("interests_json") or "[]")
        except Exception:
            interests = []

        profile_info = {
            "name": user.get("name"),
            "class_level": user.get("class_level"),
            "interests": interests,
        }

        system_prompt = (
            "You are the Financial Aid Advisor for Baymax-lite, an AI assistant "
            "that helps Hong Kong secondary school students find and understand scholarships, "
            "subsidies, grants, and financial assistance schemes.\n\n"
            "Your role:\n"
            "1. Help students discover scholarships and subsidies they may be eligible for.\n"
            "2. Explain eligibility criteria, application processes, and deadlines.\n"
            "3. Recommend suitable schemes based on the student's profile (education level, "
            "financial situation, goals).\n"
            "4. Provide accurate information ONLY from the official data below. Do NOT invent "
            "or hallucinate any scholarship that is not in the database.\n"
            "5. Always include the official URL when recommending a scheme so the student can "
            "verify and apply.\n\n"
            "Important rules:\n"
            "- The student is a Hong Kong SECONDARY school student. Only recommend schemes "
            "that are relevant and available to secondary school students. Do NOT recommend "
            "pre-primary, post-secondary, tertiary, or continuing education schemes.\n"
            "- Only recommend REAL Hong Kong scholarships/subsidies from the database below.\n"
            "- If unsure, say so and direct the student to the official WFSFAA website "
            "(https://www.wfsfaa.gov.hk) or Education Bureau.\n"
            "- Be encouraging and supportive.\n"
            "- Use clear, simple language.\n"
            "- Format responses in Markdown.\n"
            "- Math formatting: use \\(...\\) for inline math and \\[...\\] for display math.\n\n"
            f"Student profile: {profile_info!r}\n\n"
            f"{scholarship_context}\n"
        )

        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.5,
                    max_output_tokens=2048,
                ),
            )
            return (resp.text or "").strip() or "(no response)"
        except Exception as e:
            return f"AI request failed: {e}"

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    # Scheme IDs relevant for Hong Kong secondary school students
    _SECONDARY_SCHEME_IDS = {
        "tt",        # Financial Assistance Schemes for Primary & Secondary Students
        "seymf",     # Sir Edward Youde Memorial Fund
        "esf",       # Education Scholarships Fund
        "agri_sec",  # Agricultural Products Scholarship Fund – Senior Secondary
        "grantham",  # Grantham Scholarships Fund – Maintenance Grants
        "rotary",    # Hong Kong Rotary Club Students' Loan Fund
        "singtao",   # Sing Tao Charitable Foundation Students' Loan Fund
    }

    @app.route("/financial-aid")
    def financial_aid():
        user = web_context.role_required("student")
        data = web_scholarships.get_all_scholarships()
        # Only show schemes suitable for secondary school students
        schemes = [
            s for s in data.get("schemes", [])
            if s.get("id") in _SECONDARY_SCHEME_IDS
        ]
        return render_template(
            "financial_aid.html",
            user=user,
            schemes=schemes,
        )

    @app.route("/financial-aid/chat")
    def financial_aid_chat():
        user = web_context.role_required("student")
        # Find or create a financial-aid chat
        chats = web_db.list_chats(user_id=int(user["id"]), chat_type="financial_aid")
        if not chats:
            chat_id = web_db.create_chat(
                user_id=int(user["id"]),
                title="Financial Aid Advisor",
                chat_type="financial_aid",
            )
        else:
            chat_id = int(chats[0]["id"])
        return redirect(url_for("financial_aid_chat_view", chat_id=chat_id))

    @app.route("/financial-aid/chat/<int:chat_id>")
    def financial_aid_chat_view(chat_id: int):
        user = web_context.role_required("student")
        chat_row = web_db.get_chat(chat_id=chat_id, user_id=int(user["id"]))
        if not chat_row:
            return redirect(url_for("financial_aid_chat"))

        chats = web_db.list_chats(user_id=int(user["id"]), chat_type="financial_aid")
        messages = web_db.list_messages(chat_id=chat_id, limit=250)
        for m in messages:
            m["content_html"] = web_markdown.render_markdown(m.get("content") or "")

        return render_template(
            "financial_aid_chat.html",
            user=user,
            chats=chats,
            active_chat_id=chat_id,
            messages=messages,
        )

    @app.route("/financial-aid/chat/new", methods=["POST"])
    def financial_aid_chat_new():
        user = web_context.role_required("student")
        chat_id = web_db.create_chat(
            user_id=int(user["id"]),
            title="Financial Aid Advisor",
            chat_type="financial_aid",
        )
        return redirect(url_for("financial_aid_chat_view", chat_id=chat_id))

    @app.route("/api/financial-aid/chat/<int:chat_id>/send", methods=["POST"])
    def api_financial_aid_send(chat_id: int):
        user = web_context.role_required("student")
        chat_row = web_db.get_chat(chat_id=chat_id, user_id=int(user["id"]))
        if not chat_row:
            return jsonify({"ok": False, "error": "Chat not found"}), 404

        payload: dict[str, Any] = {}
        if request.is_json:
            payload = request.get_json(silent=True) or {}
        else:
            payload = dict(request.form)

        text = (payload.get("message") or "").strip()
        if not text:
            return jsonify({"ok": False, "error": "Empty message"}), 400

        web_db.add_message(chat_id=chat_id, role="user", content=text)

        # Update title from first message
        if (chat_row.get("title") or "") == "Financial Aid Advisor":
            title = text[:40].strip() or "Financial Aid"
            with web_db._connect() as conn:  # noqa: SLF001
                cur = conn.cursor()
                cur.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))
                conn.commit()

        try:
            reply = _financial_aid_reply(user=user, chat_id=chat_id, user_text=text)
        except Exception as e:
            current_app.logger.exception("Financial aid AI reply failed")
            return jsonify({"ok": False, "error": f"AI failed: {e}"}), 500

        web_db.add_message(chat_id=chat_id, role="assistant", content=reply)
        return jsonify({
            "ok": True,
            "reply": reply,
            "reply_html": web_markdown.render_markdown(reply),
        })

    @app.route("/financial-aid/chat/<int:chat_id>/delete", methods=["POST"])
    def financial_aid_chat_delete(chat_id: int):
        user = web_context.role_required("student")
        success = web_db.delete_chat(chat_id=chat_id, user_id=int(user["id"]))
        if success:
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Chat not found"}), 404

    @app.route("/api/financial-aid/refresh", methods=["POST"])
    def api_financial_aid_refresh():
        """Force re-scrape of scholarship data."""
        web_context.role_required("student")
        try:
            web_scholarships.get_all_scholarships(force_refresh=True)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
