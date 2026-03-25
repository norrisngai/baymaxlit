"""Check Your Work – AI marking engine.

Analyses a student's uploaded worksheet/writing photo via Gemini Vision,
then annotates the original image like a real teacher:
  - Red circles / underlines on mistakes
  - Yellow highlights on important points
  - Margin comments for writing tasks (line-by-line)

Returns both structured JSON feedback AND an annotated PNG image.
"""

from __future__ import annotations

import io
import json
import math
import re
import textwrap
import time
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# ── Gemini prompt templates ──────────────────────────────────────────────

_WORKSHEET_PROMPT = """\
You are a supportive and insightful Hong Kong secondary school teacher marking a student's homework.
Your goal is to help the student learn from genuine errors, not nitpick minor issues.

The student has uploaded a photo of their worksheet. Analyse the image carefully:
1. Identify every visible question and the student's written answer.
2. For each answer, decide if it is correct, partially correct, or wrong.
3. Only flag something as a "mistake" if the answer is objectively incorrect or incomplete. \
Do NOT mark correct answers that are simply phrased differently from the model answer.
4. **IGNORE all spelling errors completely.** Do NOT flag, mention, or annotate any spelling mistakes.
5. For mistakes, describe the location on the image using normalised bounding-box coordinates
   in the format [y_min, x_min, y_max, x_max] where each value is 0-1000 (0 = top/left, 1000 = bottom/right).
6. For good work (correct answers, clear working), use type "good" to acknowledge effort.

Return ONLY valid JSON (no markdown fences) with this structure:
{
  "subject_detected": "e.g. Math / English / Physics / ...",
  "annotations": [
    {
      "bbox": [y_min, x_min, y_max, x_max],
      "type": "mistake" | "highlight" | "good",
      "label": "short label (1-5 words)",
      "comment": "brief explanation of the mistake or highlight"
    }
  ],
  "overall_feedback": "2-3 sentences of overall advice (encouraging but honest)",
  "big_mistakes": ["list of the most critical mistakes to fix"],
  "tips": ["2-3 actionable tips for improvement"]
}

Rules:
- Do NOT say which answers are right or wrong explicitly in overall_feedback.
- Focus on pointing out significant mistakes and giving constructive advice.
- Keep comments concise (1 sentence each).
- If you cannot read part of the image, skip that area.
- Bounding boxes must be approximate but reasonable.
"""

_WRITING_PROMPT = """\
You are a supportive and insightful Hong Kong secondary school teacher marking a student's assignment.
Your goal is to help the student improve while respecting their unique voice.

Writing topic/question: {topic}

The student has uploaded a photo of their written work. Read it line by line and:
1. **Only annotate areas where you can see actual written words.** Never place an annotation on blank space, \
margins, or areas with no text.
2. Flag **serious grammar mistakes** as type "mistake" — these are errors that break the sentence or change \
its meaning (e.g. subject-verb disagreement, missing verb, wrong tense, run-on sentences, sentence fragments, \
wrong word usage like "their" vs "there"). Mark these in red.
3. **IGNORE all spelling errors completely.** Do NOT flag, mention, or annotate any spelling mistakes. \
Pretend every word is spelled correctly.
4. Identify **Highlights**: good vocabulary, creative ideas, strong sentences — mark as "good".
5. For phrasing that is correct but could be improved, use "highlight" with a gentle suggestion.
6. For each annotation, give the approximate bounding-box on the image using normalised coordinates \
[y_min, x_min, y_max, x_max] where each value is 0-1000 (0 = top/left, 1000 = bottom/right). \
The box MUST cover an area where words are visible.
7. For genuine grammar mistakes, provide the corrected version.

Return ONLY valid JSON (no markdown fences) with this structure:
{{
  "annotations": [
    {{
      "bbox": [y_min, x_min, y_max, x_max],
      "type": "mistake" | "highlight" | "good",
      "label": "short label (1-5 words)",
      "comment": "explanation or correction",
      "original_text": "what student wrote (if applicable)",
      "corrected_text": "corrected version (only for grammar mistakes, else null)"
    }}
  ],
  "line_by_line_comments": [
    {{
      "line_number": 1,
      "comment": "comment about this line or group of lines"
    }}
  ],
  "overall_feedback": "2-4 sentences of overall assessment (balanced: strengths + weaknesses)",
  "big_mistakes": ["only serious grammar errors that must be fixed"],
  "tips": ["2-3 actionable improvement suggestions"]
}}

Rules:
- **ONLY annotate where words exist.** Never annotate blank/empty areas of the page.
- **NEVER flag spelling errors.** Ignore spelling completely — zero annotations, zero comments.
- Only flag "mistake" for serious grammar errors that break the sentence or confuse meaning.
- Minor style preferences are NOT mistakes — use "highlight" for gentle suggestions.
- Be selective: a typical page should have at most 3-5 mistake annotations. Quality over quantity.
- Keep the tone peer-like and helpful, not pedantic.
- If you cannot read part of the handwriting, skip it silently.
"""


# ── Transcription prompt ─────────────────────────────────────────────────

_TRANSCRIBE_PROMPT = """\
You are a careful transcription assistant. The student has uploaded a photo of their handwritten work.

Your ONLY job is to type out exactly what the student has written, line by line.

Rules:
- Reproduce the student's text faithfully, including any grammar mistakes or awkward phrasing.
- Preserve the original line breaks as they appear on the page.
- If you cannot read a word clearly, write [unclear] in its place.
- Do NOT correct anything. Do NOT add commentary. Do NOT skip any lines.
- Number each line: "1: ...", "2: ...", etc.
- If there are question numbers or headings visible, include them.

Return ONLY the transcribed text, nothing else. No JSON, no markdown fences.
"""


# ── Annotation colours ───────────────────────────────────────────────────

_RED = (220, 38, 38)         # mistakes  – red circle / underline
_YELLOW = (250, 204, 21)     # highlights – yellow box
_GREEN = (34, 197, 94)       # good work  – green tick / box
_WHITE = (255, 255, 255)
_SHADOW = (0, 0, 0, 120)


# ── Public API ───────────────────────────────────────────────────────────

def transcribe_work(
    *,
    client: Any,
    types: Any,
    model_name: str,
    image_bytes: bytes,
    image_mime: str,
) -> str:
    """Send image to Gemini Vision, get a faithful line-by-line transcription.

    Returns the transcribed text as a plain string, or an empty string on failure.
    """
    if not client or not types:
        return ""

    mime = (image_mime or "image/png").strip() or "image/png"

    parts: list[Any] = []
    try:
        parts.append(types.Part.from_text(_TRANSCRIBE_PROMPT))
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
    except Exception:
        parts = [
            types.Part(text=_TRANSCRIBE_PROMPT),
            types.Part(inline_data={"mime_type": mime, "data": image_bytes}),
        ]

    for attempt in range(2):
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(temperature=0.1),
            )
            text = (resp.text or "").strip()
            if text:
                return text
        except Exception:
            if attempt == 0:
                time.sleep(1)
                continue

    return ""


def analyse_work(
    *,
    client: Any,
    types: Any,
    model_name: str,
    image_bytes: bytes,
    image_mime: str,
    is_writing: bool = False,
    topic: str = "",
    transcription: str = "",
) -> dict[str, Any]:
    """Send image to Gemini Vision, get structured analysis back.

    Returns dict with keys: annotations, overall_feedback, big_mistakes, tips,
    and optionally line_by_line_comments (for writing).
    """
    if not client or not types:
        return {"error": "AI service not available."}

    if is_writing:
        prompt_text = _WRITING_PROMPT.format(topic=topic or "(not specified)")
    else:
        prompt_text = _WORKSHEET_PROMPT

    # If we have a transcription, append it so the AI can cross-reference
    if transcription:
        prompt_text += (
            "\n\n--- TRANSCRIPTION OF STUDENT'S WORK (for reference) ---\n"
            + transcription
            + "\n--- END TRANSCRIPTION ---\n"
            "Use both the image AND this transcription to mark the work. "
            "The transcription helps you read the handwriting accurately. "
            "Bounding boxes should still refer to locations on the image."
        )

    mime = (image_mime or "image/png").strip() or "image/png"

    parts: list[Any] = []
    try:
        parts.append(types.Part.from_text(prompt_text))
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
    except Exception:
        parts = [
            types.Part(text=prompt_text),
            types.Part(inline_data={"mime_type": mime, "data": image_bytes}),
        ]

    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(temperature=0.3),
            )
            raw = (resp.text or "").strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                raw = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
                result = json.loads(raw)
            if isinstance(result, dict):
                # Post-process: drop any spelling annotations that leaked through
                # and drop annotations on empty areas (no text content)
                if "annotations" in result:
                    result["annotations"] = [
                        a for a in result["annotations"]
                        if not _is_spelling_annotation(a)
                    ]
                return result
        except Exception:
            if attempt < 2:
                time.sleep(1)
                continue

    return {"error": "Failed to analyse the image. Please try again."}


def annotate_image(
    image_bytes: bytes,
    annotations: list[dict[str, Any]],
    line_comments: list[dict[str, Any]] | None = None,
) -> bytes:
    """Draw teacher-style markings on the student's uploaded image.

    Returns PNG bytes of the annotated image.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size

    # Create an overlay for semi-transparent shapes
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    # Main drawing layer (opaque elements)
    draw = ImageDraw.Draw(img)

    # Try to load a reasonable font; fall back to default
    font_size = max(14, min(w, h) // 60)
    small_font_size = max(11, font_size - 4)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
        small_font = ImageFont.truetype("arial.ttf", small_font_size)
    except Exception:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size)
            small_font = ImageFont.truetype("DejaVuSans.ttf", small_font_size)
        except Exception:
            font = ImageFont.load_default()
            small_font = font

    line_width = max(2, min(w, h) // 300)

    for ann in annotations:
        bbox = ann.get("bbox")
        if not bbox or len(bbox) != 4:
            continue

        ann_type = ann.get("type", "mistake")
        label = ann.get("label", "")

        # Convert normalised [y_min, x_min, y_max, x_max] (0-1000) → pixels
        y_min = int(bbox[0] * h / 1000)
        x_min = int(bbox[1] * w / 1000)
        y_max = int(bbox[2] * h / 1000)
        x_max = int(bbox[3] * w / 1000)

        if ann_type == "mistake":
            # Red circle / ellipse around the mistake
            _draw_circle_or_ellipse(draw, x_min, y_min, x_max, y_max, _RED, line_width)
            # Red underline
            draw.line([(x_min, y_max), (x_max, y_max)], fill=_RED, width=line_width)
            # Label above
            if label:
                _draw_label(draw, label, x_min, max(0, y_min - font_size - 4), _RED, _WHITE, font)

        elif ann_type == "highlight":
            # Semi-transparent yellow highlight
            draw_overlay.rectangle(
                [x_min, y_min, x_max, y_max],
                fill=(250, 204, 21, 60),
            )
            if label:
                _draw_label(draw, label, x_min, max(0, y_min - font_size - 4), (180, 140, 0), _WHITE, font)

        elif ann_type == "good":
            # Green checkmark / border
            draw.rectangle([x_min, y_min, x_max, y_max], outline=_GREEN, width=line_width)
            # Draw a small tick
            cx = (x_min + x_max) // 2
            cy = y_min - font_size
            tick_size = font_size // 2
            if cy > 0:
                draw.line(
                    [(cx - tick_size, cy), (cx, cy + tick_size), (cx + tick_size * 2, cy - tick_size)],
                    fill=_GREEN,
                    width=line_width + 1,
                )
            if label:
                _draw_label(draw, label, x_max + 4, y_min, _GREEN, _WHITE, font)

    # Composite overlay onto image
    img = Image.alpha_composite(img, overlay)

    # Add line-by-line comments in the right margin if provided
    if line_comments:
        img = _add_margin_comments(img, line_comments, font, small_font)

    # Convert back to RGB for PNG output
    final = img.convert("RGB")
    buf = io.BytesIO()
    final.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── Internal helpers ─────────────────────────────────────────────────────

_SPELLING_KEYWORDS = re.compile(
    r"spell|typo|misspel|錯別字|wrong letter|letter error",
    re.IGNORECASE,
)


def _is_spelling_annotation(ann: dict) -> bool:
    """Return True if the annotation is about spelling (should be filtered out)."""
    label = (ann.get("label") or "").lower()
    comment = (ann.get("comment") or "").lower()
    text = label + " " + comment
    return bool(_SPELLING_KEYWORDS.search(text))


def _draw_circle_or_ellipse(
    draw: ImageDraw.ImageDraw,
    x_min: int, y_min: int, x_max: int, y_max: int,
    colour: tuple, width: int,
) -> None:
    """Draw an ellipse (circle if square) around a region."""
    pad = max(4, width * 2)
    draw.ellipse(
        [x_min - pad, y_min - pad, x_max + pad, y_max + pad],
        outline=colour,
        width=width,
    )


def _draw_label(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int, y: int,
    bg_colour: tuple, text_colour: tuple,
    font: ImageFont.ImageFont,
) -> None:
    """Draw a small label with a coloured background."""
    text = text[:30]  # truncate
    bbox = draw.textbbox((x, y), text, font=font)
    pad = 3
    draw.rectangle(
        [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad],
        fill=bg_colour,
    )
    draw.text((x, y), text, fill=text_colour, font=font)


def _add_margin_comments(
    img: Image.Image,
    comments: list[dict[str, Any]],
    font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> Image.Image:
    """Extend the image to the right with a margin for line-by-line comments."""
    if not comments:
        return img

    w, h = img.size
    margin_w = max(280, w // 3)
    new_img = Image.new("RGBA", (w + margin_w, h), (255, 255, 255, 255))
    new_img.paste(img, (0, 0))

    draw = ImageDraw.Draw(new_img)

    # Draw a separator line
    draw.line([(w, 0), (w, h)], fill=(200, 200, 200), width=2)

    # Space comments evenly along the height
    y_offset = 20
    line_height = max(20, h // max(len(comments), 1) - 5)

    for c in comments:
        line_num = c.get("line_number", "")
        comment = c.get("comment", "")
        if not comment:
            continue

        # Line number header
        header = f"L{line_num}:" if line_num else "•"
        draw.text((w + 8, y_offset), header, fill=_RED[:3], font=font)

        # Wrap comment text
        wrapped = textwrap.wrap(comment, width=max(20, margin_w // 8))
        y_text = y_offset + (font.size if hasattr(font, "size") else 14) + 2
        for line in wrapped[:4]:  # max 4 lines per comment
            draw.text((w + 8, y_text), line, fill=(60, 60, 60), font=small_font)
            y_text += (small_font.size if hasattr(small_font, "size") else 12) + 2

        y_offset = y_text + 10
        if y_offset > h - 30:
            break

    return new_img
