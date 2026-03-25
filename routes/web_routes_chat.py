"""Student chat routes (threads + messages)."""

from __future__ import annotations

from typing import Any

from flask import Flask, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for

import web_ai
import web_context
import web_db
import web_markdown
import web_uploads


def register(app: Flask) -> None:
    def gemini_reply(*, user: dict[str, Any], chat_id: int, user_text: str, use_web: bool = False) -> str:
        return web_ai.gemini_reply(
            client=current_app.config.get("GEMINI_CLIENT"),
            types=current_app.config.get("GEMINI_TYPES"),
            model_name=current_app.config.get("GEMINI_MODEL_NAME"),
            user=user,
            chat_id=chat_id,
            user_text=user_text,
            use_web=bool(use_web),
        )

    def gemini_reply_with_upload(
        *,
        user: dict[str, Any],
        chat_id: int,
        user_text: str,
        use_web: bool,
        upload_text: str | None,
        upload_image_bytes: bytes | None,
        upload_image_mime: str | None,
    ) -> str:
        return web_ai.gemini_reply(
            client=current_app.config.get("GEMINI_CLIENT"),
            types=current_app.config.get("GEMINI_TYPES"),
            model_name=current_app.config.get("GEMINI_MODEL_NAME"),
            user=user,
            chat_id=chat_id,
            user_text=user_text,
            use_web=bool(use_web),
            upload_text=upload_text,
            upload_image_bytes=upload_image_bytes,
            upload_image_mime=upload_image_mime,
        )

    def _to_bool(v: Any) -> bool:
        if isinstance(v, bool):
            return v
        s = str(v or "").strip().lower()
        return s in {"1", "true", "yes", "y", "on"}

    @app.route("/chat")
    def chat_home():
        user = web_context.role_required("student")
        chats = web_db.list_chats(user_id=int(user["id"]), chat_type="chat")
        if not chats:
            chat_id = web_db.create_chat(user_id=int(user["id"]), title="New chat", chat_type="chat")
            return redirect(url_for("chat", chat_id=chat_id))
        return redirect(url_for("chat", chat_id=int(chats[0]["id"])))

    @app.route("/chat/quick", methods=["GET", "POST"])
    def chat_quick():
        """Create/open a chat and immediately send a first message.

        Used by the landing page prompt: the user can type on landing, then on Send
        we create a chat, store the user message, generate the assistant reply, and
        redirect to the normal chat UI.
        """

        if request.method == "GET":
            user = web_context.current_user()
            if not user:
                return redirect(url_for("login"))
            if user.get("role") != "student":
                abort(403)

            text = str(session.pop("pending_chat_message", "") or "").strip()
            if not text:
                return redirect(url_for("chat_home"))

        else:
            text = (request.form.get("message") or request.form.get("prompt") or "").strip()
            if not text:
                return redirect(url_for("chat_home"))

            user = web_context.current_user()
            if not user:
                session["pending_chat_message"] = text
                flash("Please log in to continue.")
                return redirect(url_for("login"))
            if user.get("role") != "student":
                abort(403)

        # Create a new chat with a title derived from the first message.
        title = text[:40].strip() or "Chat"
        chat_id = web_db.create_chat(user_id=int(user["id"]), title=title, chat_type="chat")
        web_db.add_message(chat_id=chat_id, role="user", content=text)

        try:
            reply = gemini_reply(user=user, chat_id=chat_id, user_text=text, use_web=False)
        except Exception as e:
            current_app.logger.exception("Gemini reply failed")
            reply = f"Sorry — chat failed: {e}"

        web_db.add_message(chat_id=chat_id, role="assistant", content=reply)
        return redirect(url_for("chat", chat_id=chat_id))

    @app.route("/chat/new", methods=["POST"])
    def chat_new():
        user = web_context.role_required("student")
        chat_id = web_db.create_chat(user_id=int(user["id"]), title="New chat", chat_type="chat")
        return redirect(url_for("chat", chat_id=chat_id))

    @app.route("/chat/<int:chat_id>", methods=["GET", "POST"])
    def chat(chat_id: int):
        user = web_context.role_required("student")
        chat_row = web_db.get_chat(chat_id=chat_id, user_id=int(user["id"]))
        if not chat_row:
            abort(404)

        if request.method == "POST":
            text = (request.form.get("message") or "").strip()
            use_web = _to_bool(request.form.get("use_web"))
            if text:
                web_db.add_message(chat_id=chat_id, role="user", content=text)

                # Set a title based on first message (only if still default).
                if (chat_row.get("title") or "") == "New chat":
                    title = text[:40].strip()
                    # simple update inline (small + local)
                    with web_db._connect() as conn:  # noqa: SLF001
                        cur = conn.cursor()
                        cur.execute("UPDATE chats SET title = ? WHERE id = ?", (title or "Chat", chat_id))
                        conn.commit()

                try:
                    reply = gemini_reply(user=user, chat_id=chat_id, user_text=text, use_web=use_web)
                except Exception as e:
                    current_app.logger.exception("Gemini reply failed")
                    reply = f"Sorry — chat failed: {e}"
                web_db.add_message(chat_id=chat_id, role="assistant", content=reply)

            return redirect(url_for("chat", chat_id=chat_id))

        chats = web_db.list_chats(user_id=int(user["id"]), chat_type="chat")
        messages = web_db.list_messages(chat_id=chat_id, limit=250)
        # Pre-render markdown to HTML for display (safe, minimal markdown).
        for m in messages:
            m["content_html"] = web_markdown.render_markdown(m.get("content") or "")
        google_connected = bool(web_db.get_google_token(user_id=int(user["id"])))
        return render_template(
            "chat.html",
            user=user,
            chats=chats,
            active_chat_id=chat_id,
            messages=messages,
            google_connected=google_connected,
        )

    @app.route("/api/chat/<int:chat_id>/send", methods=["POST"])
    def api_chat_send(chat_id: int):
        user = web_context.role_required("student")
        chat_row = web_db.get_chat(chat_id=chat_id, user_id=int(user["id"]))
        if not chat_row:
            abort(404)

        payload: dict[str, Any] = {}
        if request.is_json:
            payload = request.get_json(silent=True) or {}
        else:
            payload = dict(request.form)

        text = (payload.get("message") or "").strip()
        use_web = _to_bool(payload.get("use_web"))

        upload_text: str | None = None
        upload_image_bytes: bytes | None = None
        upload_image_mime: str | None = None
        attachment_note = ""

        file = request.files.get("file")
        if file and file.filename:
            raw = file.read() or b""
            if len(raw) > 10 * 1024 * 1024:
                return jsonify({"ok": False, "error": "File too large (max 10MB)."}), 413
            try:
                res = web_uploads.process_upload(filename=file.filename, mime_type=file.mimetype, raw=raw)
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 400

            if res.kind == "image":
                upload_image_bytes = res.image_bytes
                upload_image_mime = res.mime_type
                attachment_note = f"\n\n[Attachment: image {res.filename}]"
            else:
                upload_text = res.extracted_text
                attachment_note = f"\n\n[Attachment: {res.filename}]"
        if not text:
            return jsonify({"ok": False, "error": "Empty message"}), 400

        web_db.add_message(chat_id=chat_id, role="user", content=text + attachment_note)

        if (chat_row.get("title") or "") == "New chat":
            title = text[:40].strip()
            with web_db._connect() as conn:  # noqa: SLF001
                cur = conn.cursor()
                cur.execute("UPDATE chats SET title = ? WHERE id = ?", (title or "Chat", chat_id))
                conn.commit()

        try:
            reply = gemini_reply_with_upload(
                user=user,
                chat_id=chat_id,
                user_text=text,
                use_web=use_web,
                upload_text=upload_text,
                upload_image_bytes=upload_image_bytes,
                upload_image_mime=upload_image_mime,
            )
        except Exception as e:
            current_app.logger.exception("Gemini reply failed")
            return jsonify({"ok": False, "error": f"Chat failed: {e}"}), 500

        web_db.add_message(chat_id=chat_id, role="assistant", content=reply)

        return jsonify({"ok": True, "reply": reply, "reply_html": web_markdown.render_markdown(reply)})

    @app.route("/chat/<int:chat_id>/delete", methods=["POST"])
    def chat_delete(chat_id: int):
        user = web_context.role_required("student")
        success = web_db.delete_chat(chat_id=chat_id, user_id=int(user["id"]))
        if success:
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Chat not found"}), 404
