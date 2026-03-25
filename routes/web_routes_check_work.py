"""Routes for the 'Check Your Work' feature."""

from __future__ import annotations

import base64
import json
from typing import Any

from flask import Flask, jsonify, render_template, request, current_app

import web_context
import web_uploads
import web_check_work


def register(app: Flask) -> None:

    @app.route("/check-work")
    def check_work():
        user = web_context.role_required("student")
        return render_template("check_work.html")

    @app.route("/api/check-work/analyse", methods=["POST"])
    def api_check_work_analyse():
        user = web_context.role_required("student")

        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"ok": False, "error": "Please upload a photo of your work."}), 400

        is_writing = request.form.get("is_writing") == "true"
        topic = (request.form.get("topic") or "").strip()

        # ── Process upload ────────────────────────────────────────────
        try:
            raw = f.read()
            result = web_uploads.process_upload(
                filename=f.filename,
                mime_type=f.content_type or "",
                raw=raw,
            )
        except Exception as e:
            return jsonify({"ok": False, "error": f"Upload error: {e}"}), 400

        if result.kind != "image":
            return jsonify({"ok": False, "error": "Please upload an image file (photo of your work)."}), 400

        image_bytes = result.image_bytes
        image_mime = result.mime_type

        if not image_bytes:
            return jsonify({"ok": False, "error": "Could not read image data."}), 400

        # ── Step 1: Transcribe what the student wrote ─────────────────
        transcription = web_check_work.transcribe_work(
            client=current_app.config.get("GEMINI_CLIENT"),
            types=current_app.config.get("GEMINI_TYPES"),
            model_name=current_app.config.get("GEMINI_MODEL_NAME"),
            image_bytes=image_bytes,
            image_mime=image_mime,
        )

        # ── Step 2: Analyse / mark the work using image + transcription
        analysis = web_check_work.analyse_work(
            client=current_app.config.get("GEMINI_CLIENT"),
            types=current_app.config.get("GEMINI_TYPES"),
            model_name=current_app.config.get("GEMINI_MODEL_NAME"),
            image_bytes=image_bytes,
            image_mime=image_mime,
            is_writing=is_writing,
            topic=topic,
            transcription=transcription,
        )

        if analysis.get("error"):
            return jsonify({"ok": False, "error": analysis["error"]}), 500

        # ── Annotate the image ────────────────────────────────────────
        annotations = analysis.get("annotations", [])
        line_comments = analysis.get("line_by_line_comments") if is_writing else None

        try:
            annotated_png = web_check_work.annotate_image(
                image_bytes=image_bytes,
                annotations=annotations,
                line_comments=line_comments,
            )
            annotated_b64 = base64.b64encode(annotated_png).decode("ascii")
        except Exception:
            annotated_b64 = None

        return jsonify({
            "ok": True,
            "transcription": transcription,
            "annotated_image": annotated_b64,
            "overall_feedback": analysis.get("overall_feedback", ""),
            "big_mistakes": analysis.get("big_mistakes", []),
            "tips": analysis.get("tips", []),
            "annotations": [
                {
                    "type": a.get("type"),
                    "label": a.get("label"),
                    "comment": a.get("comment"),
                    "corrected_text": a.get("corrected_text"),
                }
                for a in annotations
            ],
            "line_comments": analysis.get("line_by_line_comments", []),
            "subject_detected": analysis.get("subject_detected", ""),
        })
