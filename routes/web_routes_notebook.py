"""NotebookLM-style routes.

Provides:
- /notebook              – list all notebooks
- /notebook/new          – create a new notebook
- /notebook/<id>         – notebook detail (sources, chat, studio)
- /notebook/<id>/delete  – delete a notebook
- API endpoints for sources, studio generation, chat, notes
"""

from __future__ import annotations

import json
from typing import Any

from flask import (
    Flask,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import web_context
import web_db
import web_markdown
import web_notebook_ai
import web_textbooks
import web_uploads


def register(app: Flask) -> None:

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    @app.route("/notebook")
    def notebook_home():
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return redirect(url_for("login"))
        notebooks = web_db.list_notebooks(user_id=user["id"])
        return render_template(
            "notebook.html",
            title="Notebook",
            notebooks=notebooks,
        )

    @app.route("/notebook/new", methods=["POST"])
    def notebook_new():
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return redirect(url_for("login"))
        title = (request.form.get("title") or "").strip() or "Untitled notebook"
        nb_id = web_db.create_notebook(user_id=user["id"], title=title)
        return redirect(url_for("notebook_detail", notebook_id=nb_id))

    @app.route("/notebook/<int:notebook_id>")
    def notebook_detail(notebook_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return redirect(url_for("login"))
        nb = web_db.get_notebook(notebook_id=notebook_id, user_id=user["id"])
        if not nb:
            return redirect(url_for("notebook_home"))

        sources = web_db.list_notebook_sources(notebook_id=notebook_id)
        outputs = web_db.list_notebook_outputs(notebook_id=notebook_id)
        notes = web_db.list_notebook_notes(notebook_id=notebook_id)
        notebooks = web_db.list_notebooks(user_id=user["id"])

        # Render output content as HTML
        for o in outputs:
            o["content_html"] = web_markdown.render_markdown(o.get("content") or "")

        studio_types = web_notebook_ai.get_studio_types()

        # Textbook data for the add-source modal
        textbook_subjects = web_textbooks.get_subjects()
        textbooks_json = json.dumps(web_textbooks.HK_TEXTBOOKS, ensure_ascii=False)

        return render_template(
            "notebook_detail.html",
            title=nb["title"],
            notebook=nb,
            notebooks=notebooks,
            sources=sources,
            outputs=outputs,
            notes=notes,
            studio_types=studio_types,
            textbook_subjects=textbook_subjects,
            textbooks_json=textbooks_json,
        )

    @app.route("/notebook/<int:notebook_id>/delete", methods=["POST"])
    def notebook_delete(notebook_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        web_db.delete_notebook(notebook_id=notebook_id, user_id=user["id"])
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.content_type == "application/json":
            return jsonify({"ok": True})
        return redirect(url_for("notebook_home"))

    # ------------------------------------------------------------------
    # API: Notebook title
    # ------------------------------------------------------------------

    @app.route("/api/notebook/<int:notebook_id>/title", methods=["POST"])
    def api_notebook_title(notebook_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify({"ok": False, "error": "Title required"}), 400
        web_db.update_notebook_title(notebook_id=notebook_id, user_id=user["id"], title=title)
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # API: Sources
    # ------------------------------------------------------------------

    @app.route("/api/notebook/<int:notebook_id>/source/upload", methods=["POST"])
    def api_notebook_upload_source(notebook_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        nb = web_db.get_notebook(notebook_id=notebook_id, user_id=user["id"])
        if not nb:
            return jsonify({"ok": False, "error": "Notebook not found"}), 404

        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"ok": False, "error": "No file uploaded"}), 400

        try:
            raw = f.read()
            result = web_uploads.process_upload(
                filename=f.filename,
                mime_type=f.content_type or "",
                raw=raw,
            )
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        if result.kind == "image":
            return jsonify({"ok": False, "error": "Images are not supported as notebook sources. Upload PDFs, DOCX, or text files."}), 400

        source_id = web_db.add_notebook_source(
            notebook_id=notebook_id,
            source_type="upload",
            title=result.filename,
            content=result.extracted_text,
            meta={"mime_type": result.mime_type, "kind": result.kind},
        )

        return jsonify({
            "ok": True,
            "source": {
                "id": source_id,
                "title": result.filename,
                "source_type": "upload",
                "content_preview": (result.extracted_text or "")[:200],
            },
        })

    @app.route("/api/notebook/<int:notebook_id>/source/textbook", methods=["POST"])
    def api_notebook_textbook_source(notebook_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        nb = web_db.get_notebook(notebook_id=notebook_id, user_id=user["id"])
        if not nb:
            return jsonify({"ok": False, "error": "Notebook not found"}), 404

        data = request.get_json(silent=True) or {}
        subject = (data.get("subject") or "").strip()
        textbook_id = (data.get("textbook_id") or "").strip()
        chapter = (data.get("chapter") or "").strip()
        page_range = (data.get("page_range") or "").strip()

        if not subject or not textbook_id or not chapter:
            return jsonify({"ok": False, "error": "Subject, textbook, and chapter are required"}), 400

        title, content = web_textbooks.build_textbook_source_content(
            subject=subject,
            textbook_id=textbook_id,
            chapter=chapter,
            page_range=page_range,
        )

        source_id = web_db.add_notebook_source(
            notebook_id=notebook_id,
            source_type="textbook",
            title=title,
            content=content,
            meta={
                "subject": subject,
                "textbook_id": textbook_id,
                "chapter": chapter,
                "page_range": page_range,
            },
        )

        return jsonify({
            "ok": True,
            "source": {
                "id": source_id,
                "title": title,
                "source_type": "textbook",
                "content_preview": content[:200],
            },
        })

    @app.route("/api/notebook/<int:notebook_id>/source/paste", methods=["POST"])
    def api_notebook_paste_source(notebook_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        nb = web_db.get_notebook(notebook_id=notebook_id, user_id=user["id"])
        if not nb:
            return jsonify({"ok": False, "error": "Notebook not found"}), 404

        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip() or "Pasted notes"
        content = (data.get("content") or "").strip()

        if not content:
            return jsonify({"ok": False, "error": "Content is required"}), 400

        source_id = web_db.add_notebook_source(
            notebook_id=notebook_id,
            source_type="paste",
            title=title,
            content=content,
        )

        return jsonify({
            "ok": True,
            "source": {
                "id": source_id,
                "title": title,
                "source_type": "paste",
                "content_preview": content[:200],
            },
        })

    @app.route("/api/notebook/<int:notebook_id>/source/<int:source_id>/delete", methods=["POST"])
    def api_notebook_delete_source(notebook_id, source_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        web_db.delete_notebook_source(source_id=source_id, notebook_id=notebook_id)
        return jsonify({"ok": True})

    @app.route("/api/notebook/<int:notebook_id>/source/<int:source_id>")
    def api_notebook_get_source(notebook_id, source_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        src = web_db.get_notebook_source(source_id=source_id)
        if not src or src.get("notebook_id") != notebook_id:
            return jsonify({"ok": False, "error": "Source not found"}), 404
        return jsonify({
            "ok": True,
            "source": {
                "id": src["id"],
                "title": src["title"],
                "source_type": src["source_type"],
                "content": src["content"],
                "meta": json.loads(src.get("meta_json") or "{}"),
            },
        })

    # ------------------------------------------------------------------
    # API: Studio generation
    # ------------------------------------------------------------------

    @app.route("/api/notebook/<int:notebook_id>/generate", methods=["POST"])
    def api_notebook_generate(notebook_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        nb = web_db.get_notebook(notebook_id=notebook_id, user_id=user["id"])
        if not nb:
            return jsonify({"ok": False, "error": "Notebook not found"}), 404

        data = request.get_json(silent=True) or {}
        output_type = (data.get("output_type") or "").strip()
        source_ids = data.get("source_ids") or []

        valid_types = {st["id"] for st in web_notebook_ai.get_studio_types()}
        if output_type not in valid_types:
            return jsonify({"ok": False, "error": f"Invalid output type: {output_type}"}), 400

        # Validate source_ids are ints
        try:
            source_ids = [int(sid) for sid in source_ids] if source_ids else []
        except (ValueError, TypeError):
            source_ids = []

        client = current_app.config.get("GEMINI_CLIENT")
        types_mod = current_app.config.get("GEMINI_TYPES")
        model_name = current_app.config.get("GEMINI_PRO_MODEL_NAME") or current_app.config.get("GEMINI_MODEL_NAME")
        fallback_model_name = current_app.config.get("GEMINI_MODEL_NAME")
        image_model_name = current_app.config.get("GEMINI_IMAGE_MODEL_NAME")

        result = web_notebook_ai.generate_studio_output(
            client=client,
            types=types_mod,
            model_name=model_name,
            fallback_model_name=fallback_model_name,
            image_model_name=image_model_name,
            notebook_id=notebook_id,
            output_type=output_type,
            source_ids=source_ids or None,
        )

        if result.get("ok") and not result.get("image_b64"):
            result["content_html"] = web_markdown.render_markdown(result.get("content") or "")

        return jsonify(result)

    # ------------------------------------------------------------------
    # API: Chat with sources
    # ------------------------------------------------------------------

    @app.route("/api/notebook/<int:notebook_id>/chat", methods=["POST"])
    def api_notebook_chat(notebook_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        nb = web_db.get_notebook(notebook_id=notebook_id, user_id=user["id"])
        if not nb:
            return jsonify({"ok": False, "error": "Notebook not found"}), 404

        data = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()
        chat_history = data.get("history") or []
        source_ids = data.get("source_ids") or []

        if not message:
            return jsonify({"ok": False, "error": "Message is required"}), 400

        try:
            source_ids = [int(sid) for sid in source_ids] if source_ids else []
        except (ValueError, TypeError):
            source_ids = []

        client = current_app.config.get("GEMINI_CLIENT")
        types_mod = current_app.config.get("GEMINI_TYPES")
        model_name = current_app.config.get("GEMINI_PRO_MODEL_NAME") or current_app.config.get("GEMINI_MODEL_NAME")
        fallback_model_name = current_app.config.get("GEMINI_MODEL_NAME")

        reply = web_notebook_ai.notebook_chat_reply(
            client=client,
            types=types_mod,
            model_name=model_name,
            fallback_model_name=fallback_model_name,
            notebook_id=notebook_id,
            user_text=message,
            chat_history=chat_history,
            source_ids=source_ids or None,
        )

        return jsonify({
            "ok": True,
            "reply": reply,
            "reply_html": web_markdown.render_markdown(reply),
        })

    # ------------------------------------------------------------------
    # API: Notes
    # ------------------------------------------------------------------

    @app.route("/api/notebook/<int:notebook_id>/note/add", methods=["POST"])
    def api_notebook_add_note(notebook_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        nb = web_db.get_notebook(notebook_id=notebook_id, user_id=user["id"])
        if not nb:
            return jsonify({"ok": False, "error": "Notebook not found"}), 404

        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip() or "Untitled note"
        content = (data.get("content") or "").strip()

        note_id = web_db.add_notebook_note(
            notebook_id=notebook_id,
            title=title,
            content=content,
        )

        return jsonify({"ok": True, "note_id": note_id})

    @app.route("/api/notebook/<int:notebook_id>/note/<int:note_id>/update", methods=["POST"])
    def api_notebook_update_note(notebook_id, note_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip() or "Untitled note"
        content = (data.get("content") or "").strip()

        web_db.update_notebook_note(note_id=note_id, title=title, content=content)
        return jsonify({"ok": True})

    @app.route("/api/notebook/<int:notebook_id>/note/<int:note_id>/delete", methods=["POST"])
    def api_notebook_delete_note(notebook_id, note_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        web_db.delete_notebook_note(note_id=note_id, notebook_id=notebook_id)
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # API: Outputs
    # ------------------------------------------------------------------

    @app.route("/api/notebook/<int:notebook_id>/output/<int:output_id>")
    def api_notebook_get_output(notebook_id, output_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        o = web_db.get_notebook_output(output_id=output_id)
        if not o or o.get("notebook_id") != notebook_id:
            return jsonify({"ok": False, "error": "Output not found"}), 404

        output_data = {
            "id": o["id"],
            "output_type": o["output_type"],
            "title": o["title"],
            "content": o["content"],
            "content_html": web_markdown.render_markdown(o.get("content") or ""),
        }

        # Mind map outputs store image data as JSON in the content field
        if o["output_type"] == "mind_map":
            try:
                import json as _json
                img_data = _json.loads(o["content"])
                if img_data.get("image_b64"):
                    output_data["image_b64"] = img_data["image_b64"]
                    output_data["mime_type"] = img_data.get("mime_type", "image/png")
                    output_data["content"] = ""
                    output_data["content_html"] = ""
            except (ValueError, KeyError):
                pass  # Old format or non-JSON content, fall through to normal display

        return jsonify({"ok": True, "output": output_data})

    @app.route("/api/notebook/<int:notebook_id>/output/<int:output_id>/delete", methods=["POST"])
    def api_notebook_delete_output(notebook_id, output_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        web_db.delete_notebook_output(output_id=output_id, notebook_id=notebook_id)
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # API: Textbook data (for dynamic dropdowns)
    # ------------------------------------------------------------------

    @app.route("/api/textbooks/<subject>")
    def api_textbooks_for_subject(subject):
        books = web_textbooks.get_textbooks_for_subject(subject)
        return jsonify({"ok": True, "textbooks": books})

    # ------------------------------------------------------------------
    # API: Get quiz info from selected sources (subject + topic)
    # ------------------------------------------------------------------

    @app.route("/api/notebook/<int:notebook_id>/quiz-info", methods=["POST"])
    def api_notebook_quiz_info(notebook_id):
        user = web_context.current_user()
        if not user or user.get("role") != "student":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        nb = web_db.get_notebook(notebook_id=notebook_id, user_id=user["id"])
        if not nb:
            return jsonify({"ok": False, "error": "Notebook not found"}), 404

        data = request.get_json(silent=True) or {}
        source_ids = data.get("source_ids") or []
        try:
            source_ids = [int(sid) for sid in source_ids] if source_ids else []
        except (ValueError, TypeError):
            source_ids = []

        sources = web_db.list_notebook_sources(notebook_id=notebook_id)
        if source_ids:
            id_set = set(source_ids)
            sources = [s for s in sources if s["id"] in id_set]

        # Try to extract subject and topic from textbook sources first
        subject = ""
        topic = ""
        for src in sources:
            if src.get("source_type") == "textbook":
                meta = {}
                try:
                    meta = json.loads(src.get("meta_json") or "{}")
                except Exception:
                    pass
                subject = meta.get("subject", "")
                topic = meta.get("chapter", "")
                if subject and topic:
                    break

        # Fallback: use the source title
        if not topic and sources:
            topic = sources[0].get("title", "")

        return jsonify({"ok": True, "subject": subject, "topic": topic})
