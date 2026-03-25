"""AI generation helpers for the Notebook (NotebookLM-style) feature.

Generates studio outputs from notebook sources:
- Summary
- Study Guide
- Flashcards (JSON for interactive card UI)
- Mind Map (AI-generated image)
- FAQ
- Video Overview (script-based)
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

import web_db


# ---------------------------------------------------------------------------
# Studio output types
# ---------------------------------------------------------------------------

STUDIO_TYPES: list[dict[str, str]] = [
    {"id": "summary", "label": "Summary", "icon": "📝", "description": "A concise summary of your selected sources."},
    {"id": "study_guide", "label": "Study Guide", "icon": "📖", "description": "A comprehensive study guide with key concepts."},
    {"id": "flashcards", "label": "Flashcards", "icon": "🗂️", "description": "Interactive flashcards for active recall."},
    {"id": "mind_map", "label": "Mind Map", "icon": "🧠", "description": "An AI-generated mind map image of connected concepts."},
    {"id": "faq", "label": "FAQ", "icon": "💬", "description": "Frequently asked questions & answers."},
    {"id": "video_overview", "label": "Video Overview", "icon": "🎬", "description": "A teaching video script for the selected material."},
]


def get_studio_types() -> list[dict[str, str]]:
    return STUDIO_TYPES


def _build_source_context(notebook_id: int, source_ids: list[int] | None = None) -> str:
    """Combine selected (or all) sources in a notebook into a single context string."""
    sources = web_db.list_notebook_sources(notebook_id=notebook_id)
    if not sources:
        return ""

    if source_ids:
        id_set = set(source_ids)
        sources = [s for s in sources if s["id"] in id_set]

    if not sources:
        return ""

    parts: list[str] = []
    for i, src in enumerate(sources, 1):
        header = f"=== Source {i}: {src['title']} (type: {src['source_type']}) ==="
        parts.append(header)
        parts.append(src.get("content") or "(empty)")
        parts.append("")

    return "\n".join(parts)


def _build_generation_prompt(*, output_type: str, source_context: str) -> str:
    """Build the user prompt for generating a specific studio output type."""

    prompts: dict[str, str] = {
        "summary": (
            "Based on all the source materials below, write a concise but comprehensive summary. "
            "Cover all major topics, key concepts and important details. "
            "Use clear headings and bullet points. Format in Markdown."
        ),
        "study_guide": (
            "Based on all the source materials below, create a comprehensive study guide. "
            "Include:\n"
            "- Key concepts and definitions\n"
            "- Important formulas or rules\n"
            "- Step-by-step explanations of complex topics\n"
            "- Tips for remembering key information\n"
            "- Practice problems with solutions\n"
            "Format in Markdown with clear headings."
        ),
        "flashcards": (
            "Based on all the source materials below, create a set of flashcards for study.\n"
            "Generate at least 15 flashcards.\n"
            "You MUST respond with ONLY a valid JSON array. No markdown, no explanation, no code fences.\n"
            "Each element must be an object with exactly two keys: \"q\" (the question) and \"a\" (the answer).\n"
            "Example:\n"
            '[{"q":"What is Newton\'s first law?","a":"An object at rest stays at rest, and an object in motion stays in motion unless acted upon by an external force."}]\n'
            "Cover all key concepts, definitions, formulas, and important facts.\n"
            "Return ONLY the JSON array, nothing else."
        ),
        "mind_map": (
            "Based on all the source materials below, generate a beautiful, detailed MIND MAP IMAGE.\n"
            "The mind map should:\n"
            "- Have a central topic node in the middle\n"
            "- Branch out into major topics with colorful, distinct colored nodes\n"
            "- Each branch should have sub-topics and key details\n"
            "- Use clear, readable text labels on each node (short phrases, under 30 chars)\n"
            "- Have connecting lines between related concepts\n"
            "- Look professional, clean, and visually appealing like an infographic\n"
            "- Use a dark background with bright colorful nodes\n"
            "- Include all major concepts from the source materials\n"
            "Generate the mind map as an IMAGE."
        ),
        "faq": (
            "Based on all the source materials below, create a comprehensive FAQ (Frequently Asked Questions) section. "
            "Generate at least 10 questions that a student might ask about this material. "
            "Format each as:\n\n"
            "### Q: [question]\n\n"
            "[detailed answer]\n\n"
            "Cover fundamental concepts, common confusions, and exam-relevant topics."
        ),
        "video_overview": (
            "Based on all the source materials below, create a detailed teaching video script.\n"
            "The script should be structured as a video lesson that a student can follow.\n\n"
            "Format the video script in Markdown with these sections:\n\n"
            "# Video: [Topic Title]\n\n"
            "## Introduction (0:00 - 0:30)\n"
            "[Opening hook and overview of what will be covered]\n\n"
            "## Section 1: [Key Concept] (0:30 - X:XX)\n"
            "[Detailed explanation with examples]\n\n"
            "## Section 2: [Key Concept] (X:XX - X:XX)\n"
            "[Detailed explanation with examples]\n\n"
            "... (continue for all major topics)\n\n"
            "## Summary & Key Takeaways\n"
            "[Bullet points of the most important things to remember]\n\n"
            "## Practice Questions\n"
            "[2-3 practice questions for the student to try]\n\n"
            "Make it engaging, clear, and suitable for Hong Kong secondary school students. "
            "Include visual cue suggestions in [brackets] like [Show diagram of...] or [Display formula...]."
        ),
    }

    instruction = prompts.get(output_type, prompts["summary"])

    return (
        f"{instruction}\n\n"
        f"--- SOURCE MATERIALS ---\n\n"
        f"{source_context}\n\n"
        f"--- END SOURCE MATERIALS ---"
    )


def generate_studio_output(
    *,
    client: Any,
    types: Any,
    model_name: str,
    fallback_model_name: str | None = None,
    image_model_name: str | None = None,
    notebook_id: int,
    output_type: str,
    source_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Generate a studio output and save it to the database.

    Returns {"ok": True, "output_id": int, "content": str} or {"ok": False, "error": str}.
    """
    if not client or not types:
        return {"ok": False, "error": "AI is not configured. Please set GOOGLE_GEMINI_API_KEY."}

    source_context = _build_source_context(notebook_id, source_ids=source_ids)
    if not source_context.strip():
        return {"ok": False, "error": "No sources selected. Select sources on the left panel first."}

    # Find label for this type
    label = output_type.replace("_", " ").title()
    for st in STUDIO_TYPES:
        if st["id"] == output_type:
            label = st["label"]
            break

    user_prompt = _build_generation_prompt(output_type=output_type, source_context=source_context)

    system_prompt = (
        "You are a study assistant that generates high-quality educational content from student notes and textbook materials. "
        "You are helping Hong Kong secondary school (DSE) students study. "
        "Always be accurate, comprehensive, and well-organised. "
    )

    # Flashcards need raw JSON format; mind_map uses image gen; others use Markdown
    if output_type == "flashcards":
        system_prompt += "You output ONLY valid JSON arrays. No markdown, no code fences, no extra text."
    elif output_type == "mind_map":
        system_prompt += "You generate beautiful mind map images."
    else:
        system_prompt += (
            "Format your output in clean Markdown. "
            "Math formatting: use \\(...\\) for inline math and \\[...\\] for display math. "
            "Do NOT use dollar-sign delimiters."
        )

    # Mind map uses image generation model
    if output_type == "mind_map" and image_model_name:
        try:
            result = _generate_mind_map_image(
                client=client,
                types=types,
                image_model_name=image_model_name,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
            )
            if result.get("ok"):
                image_b64 = result.get("image_b64", "")
                mime_type = result.get("mime_type", "image/png")
                # Store image data as JSON in content field for later retrieval
                stored = json.dumps({"image_b64": image_b64, "mime_type": mime_type})
                title = f"{label} — {_get_notebook_title(notebook_id)}"
                output_id = web_db.add_notebook_output(
                    notebook_id=notebook_id,
                    output_type=output_type,
                    title=title,
                    content=stored,
                )
                return {
                    "ok": True,
                    "output_id": output_id,
                    "content": result["content"],
                    "output_type": output_type,
                    "image_b64": image_b64,
                    "mime_type": mime_type,
                }
            else:
                return result
        except Exception as e:
            return {"ok": False, "error": f"AI image generation failed: {e}"}

    try:
        resp = _generate_with_fallback(
            client=client,
            types=types,
            model_name=model_name,
            fallback_model_name=fallback_model_name,
            contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.5,
                max_output_tokens=4096,
            ),
        )
        content = (resp.text or "").strip() or "(No content generated)"
    except Exception as e:
        return {"ok": False, "error": f"AI generation failed: {e}"}

    # Post-processing for flashcards: strip any code fences
    if output_type == "flashcards":
        content = _clean_json_response(content)

    # Save to database
    title = f"{label} — {_get_notebook_title(notebook_id)}"
    output_id = web_db.add_notebook_output(
        notebook_id=notebook_id,
        output_type=output_type,
        title=title,
        content=content,
    )

    return {"ok": True, "output_id": output_id, "content": content, "output_type": output_type}


def notebook_chat_reply(
    *,
    client: Any,
    types: Any,
    model_name: str,
    fallback_model_name: str | None = None,
    notebook_id: int,
    user_text: str,
    chat_history: list[dict[str, str]],
    source_ids: list[int] | None = None,
) -> str:
    """Chat with notebook sources — like NotebookLM's chat feature."""
    if not client or not types:
        return "AI is not configured. Please set GOOGLE_GEMINI_API_KEY."

    source_context = _build_source_context(notebook_id, source_ids=source_ids)

    system_prompt = (
        "You are a study assistant that answers questions based on the student's notebook sources. "
        "You are helping Hong Kong secondary school (DSE) students study. "
        "Answer ONLY based on the source materials provided below. "
        "If the answer is not in the sources, say so clearly. "
        "Be concise but thorough. Format in Markdown. "
        "Math formatting: use \\(...\\) for inline math and \\[...\\] for display math.\n\n"
        f"--- SOURCE MATERIALS ---\n\n{source_context}\n\n--- END SOURCE MATERIALS ---"
    )

    contents = []
    for msg in chat_history:
        role = "user" if msg.get("role") == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg.get("content") or "")]))
    contents.append(types.Content(role="user", parts=[types.Part(text=user_text)]))

    try:
        resp = _generate_with_fallback(
            client=client,
            types=types,
            model_name=model_name,
            fallback_model_name=fallback_model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=2048,
            ),
        )
        return (resp.text or "").strip() or "(no response)"
    except Exception as e:
        return f"AI request failed: {e}"


def _generate_mind_map_image(
    *,
    client: Any,
    types: Any,
    image_model_name: str,
    user_prompt: str,
    system_prompt: str,
) -> dict[str, Any]:
    """Call the Gemini image-generation model and return base64 image data."""
    resp = client.models.generate_content(
        model=image_model_name,
        contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_modalities=["TEXT", "IMAGE"],
        ),
    )

    image_b64: str | None = None
    mime_type = "image/png"
    text_parts: list[str] = []

    for part in resp.candidates[0].content.parts:
        if part.inline_data:
            image_b64 = base64.b64encode(part.inline_data.data).decode("utf-8")
            mime_type = part.inline_data.mime_type or "image/png"
        elif part.text:
            text_parts.append(part.text)

    if not image_b64:
        return {"ok": False, "error": "The AI model did not return an image. Please try again."}

    return {
        "ok": True,
        "content": "\n".join(text_parts) or "Mind Map",
        "image_b64": image_b64,
        "mime_type": mime_type,
    }


def _should_fallback_model(error: Exception) -> bool:
    message = str(error)
    fallback_markers = (
        "RESOURCE_EXHAUSTED",
        "FAILED_PRECONDITION",
        "quota",
        "quota exceeded",
        "retry in",
        "location is not supported",
    )
    lowered = message.lower()
    return any(marker.lower() in lowered for marker in fallback_markers)


def _generate_with_fallback(
    *,
    client: Any,
    types: Any,
    model_name: str,
    fallback_model_name: str | None,
    contents: list[Any],
    config: Any,
) -> Any:
    try:
        return client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )
    except Exception as exc:
        if not fallback_model_name or fallback_model_name == model_name or not _should_fallback_model(exc):
            raise
        return client.models.generate_content(
            model=fallback_model_name,
            contents=contents,
            config=config,
        )


def _clean_json_response(text: str) -> str:
    """Strip markdown code fences from a JSON response."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text)
    return text.strip()


def _clean_mermaid_response(text: str) -> str:
    """Strip markdown code fences from a Mermaid response."""
    text = text.strip()
    text = re.sub(r'^```(?:mermaid)?\s*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text)
    return text.strip()


def _get_notebook_title(notebook_id: int) -> str:
    """Get notebook title (best-effort)."""
    try:
        from flask import session
        user_id = session.get("user_id", 0)
        nb = web_db.get_notebook(notebook_id=notebook_id, user_id=user_id)
        return nb.get("title", "Notebook") if nb else "Notebook"
    except Exception:
        return "Notebook"
