"""AI-powered quiz generation using Gemini, with HKDSE knowledge integration."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import web_hkdse_knowledge as hkdse


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (value or "").strip().lower())).strip()


def _extract_answer_phrases(value: str) -> list[str]:
    raw = (value or "").strip().lower()
    if not raw:
        return []
    parts = re.split(r"\s*(?:,|/|;|\bor\b|\band\b)\s*", raw)
    phrases: list[str] = []
    for part in parts:
        cleaned = _normalize_text(part)
        if cleaned:
            phrases.append(cleaned)
    return phrases


def _has_mixed_correctness(*, student_answer: str, reference_answer: str) -> bool:
    student_phrases = _extract_answer_phrases(student_answer)
    if len(student_phrases) < 2:
        return False

    reference_phrases = _extract_answer_phrases(reference_answer)
    if not reference_phrases:
        reference_norm = _normalize_text(reference_answer)
        reference_phrases = [reference_norm] if reference_norm else []
    if not reference_phrases:
        return False

    def is_phrase_accepted(phrase: str) -> bool:
        phrase_tokens = {tok for tok in phrase.split() if len(tok) >= 3}
        for ref in reference_phrases:
            if phrase == ref or phrase in ref or ref in phrase:
                return True
            ref_tokens = {tok for tok in ref.split() if len(tok) >= 3}
            if phrase_tokens and ref_tokens and phrase_tokens <= ref_tokens:
                return True
        return False

    accepted = [phrase for phrase in student_phrases if is_phrase_accepted(phrase)]
    rejected = [phrase for phrase in student_phrases if not is_phrase_accepted(phrase)]
    return bool(accepted and rejected)


def _fallback_short_answer_grade(*, student_answer: str, reference_answer: str) -> dict[str, Any]:
    student_norm = _normalize_text(student_answer)
    reference_norm = _normalize_text(reference_answer)
    mixed_correctness = _has_mixed_correctness(student_answer=student_answer, reference_answer=reference_answer)

    if not student_norm:
        return {"score": 0, "comment": "No answer provided."}
    if student_norm == reference_norm:
        return {"score": 2, "comment": "The main idea matches the expected answer."}
    if reference_norm and reference_norm in student_norm and not mixed_correctness:
        return {"score": 2, "comment": "Your answer includes the expected main idea."}

    student_tokens = {tok for tok in student_norm.split() if len(tok) >= 4}
    reference_tokens = {tok for tok in reference_norm.split() if len(tok) >= 4}
    if not reference_tokens:
        return {"score": 0, "comment": "The answer could not be verified automatically."}

    overlap = len(student_tokens & reference_tokens)
    ratio = overlap / max(1, len(reference_tokens))
    if mixed_correctness and ratio >= 0.2:
        return {"score": 1, "comment": "Part of your answer is correct, but you also included an incorrect option."}
    if ratio >= 0.55:
        return {"score": 2, "comment": "Your answer covers the key idea well enough for full credit."}
    if ratio >= 0.2:
        return {"score": 1, "comment": "Your answer is partly correct, but it is incomplete or misses an important point."}
    return {"score": 0, "comment": "Your answer does not show the expected main idea."}


def grade_short_answer_responses(
    *,
    client: Any,
    types: Any,
    model_name: str,
    subject: str,
    topic: str,
    class_level: str,
    items: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Grade short answers with 0/1/2 marks using AI, with heuristic fallback."""

    if not items:
        return {}

    fallback = {
        str(item.get("id")): _fallback_short_answer_grade(
            student_answer=str(item.get("student_answer") or ""),
            reference_answer=str(item.get("reference_answer") or ""),
        )
        for item in items
    }

    if not client or not types or not model_name:
        return fallback

    prompt_payload = [
        {
            "id": str(item.get("id") or ""),
            "question": str(item.get("question") or ""),
            "student_answer": str(item.get("student_answer") or ""),
            "reference_answer": str(item.get("reference_answer") or ""),
            "explanation": str(item.get("explanation") or ""),
        }
        for item in items
    ]

    prompt = (
        "You are grading student short-answer quiz responses.\n"
        "Return ONLY valid JSON. No markdown, no extra text.\n\n"
        f"Subject: {subject}\n"
        f"Topic: {topic}\n"
        f"Class level: {class_level}\n\n"
        "Scoring rubric for EACH answer:\n"
        "- Give 2 marks if the student's main idea is correct, even if wording differs from the reference answer.\n"
        "- Give 1 mark if the answer is partly correct, incomplete, vague, or has some incorrect detail mixed in.\n"
        "- Give 0 marks if the answer is wrong, off-topic, or misses the core idea.\n"
        "- IMPORTANT: if the student gives multiple answers and one is correct but another is clearly wrong, do NOT give full marks. That should be 1 mark.\n"
        "- Prefer meaning over exact wording.\n"
        "- The maximum score is 2 marks for every short-answer question.\n"
        "- comment must be brief, specific, and directly about why the student got that score.\n\n"
        "Return a JSON array where each item has exactly these keys:\n"
        '[{"id":"...","score":0|1|2,"comment":"..."}]\n\n'
        f"Responses to grade:\n{json.dumps(prompt_payload, ensure_ascii=False)}"
    )

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(temperature=0.2),
            )
            raw = (response.text or "").strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                raw = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
                parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ValueError("Expected list response")

            graded: dict[str, dict[str, Any]] = {}
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "").strip()
                if not item_id:
                    continue
                try:
                    score = int(item.get("score"))
                except Exception:
                    score = -1
                if score not in (0, 1, 2):
                    continue
                comment = str(item.get("comment") or "").strip() or fallback.get(item_id, {}).get("comment", "")
                source_item = next((row for row in items if str(row.get("id") or "") == item_id), None)
                if source_item and score == 2 and _has_mixed_correctness(
                    student_answer=str(source_item.get("student_answer") or ""),
                    reference_answer=str(source_item.get("reference_answer") or ""),
                ):
                    score = 1
                    if not comment:
                        comment = "Part of your answer is correct, but you also included an incorrect option."
                graded[item_id] = {"score": score, "comment": comment}

            if graded:
                for item_id, fb in fallback.items():
                    graded.setdefault(item_id, fb)
                return graded
        except Exception:
            if attempt == 0:
                time.sleep(0.6)
                continue
            break

    return fallback


def generate_quiz(
    *,
    client: Any,
    types: Any,
    model_name: str,
    subject: str,
    topic: str,
    difficulty: str,
    class_level: str,
    test_mode: str = "standard",
    num_questions: int = 8,
) -> list[dict[str, Any]]:
    """Generate quiz questions via Gemini with HKDSE-style prompts.

    Returns a list of question dicts:
      {
        "id": 1,
        "type": "mcq" | "true_false" | "short_answer",
        "question": "...",
        "options": ["A", "B", "C", "D"] | null,
        "correct_answer": "...",
        "explanation": "...",
        "hint": "..."
      }
    """
    if not client or not types:
        return []

    # ── Parse form number ─────────────────────────────────────────────
    form_number = 4
    m = re.match(r"(?:F|FORM)?\s*(\d+)", (class_level or "").strip(), re.IGNORECASE)
    if m:
        form_number = int(m.group(1))

    # ── Difficulty guide (layered: form descriptor + user difficulty) ──
    form_desc = hkdse.get_form_descriptor(form_number)

    difficulty_guide = {
        "basic": (
            f"{form_desc}\n"
            "Within this form level, use the EASIER end of the spectrum. "
            "Focus on recall, definitions, and straightforward comprehension."
        ),
        "intermediate": (
            f"{form_desc}\n"
            "Within this form level, use MID-RANGE difficulty. "
            "Include application, simple analysis, and some multi-step problems."
        ),
        "advanced": (
            f"{form_desc}\n"
            "Within this form level, use the HARDER end of the spectrum. "
            "Include critical thinking, multi-step reasoning, and evaluation."
        ),
    }
    diff_text = difficulty_guide.get(difficulty, difficulty_guide["intermediate"])

    # ── Subject-specific HKDSE knowledge ──────────────────────────────
    subj_knowledge = hkdse.get_subject_knowledge(subject)
    style_guide = subj_knowledge.get("style_guide", "")
    exemplars = subj_knowledge.get("exemplar_stems", [])
    marking_notes = subj_knowledge.get("marking_notes", {}).get(test_mode, "")

    # Question type mix
    type_mix = subj_knowledge.get("question_type_mix", {}).get(test_mode, {})

    # ── Build question-type rules ─────────────────────────────────────
    if test_mode == "mc_only":
        type_rules = (
            "- ALL questions must be type 'mcq' (multiple choice).\n"
            "- Provide exactly 4 options labelled A, B, C, D.\n"
            "- Each question must have exactly ONE correct answer.\n"
        )
    elif test_mode == "reading":
        type_rules = (
            "- Include a MIX of question types: multiple choice (mcq), true/false (true_false), and short answer (short_answer).\n"
            "- For READING tests, first generate a reading passage (about 250-400 words) relevant to the topic.\n"
            "  Include the passage as the 'question' field of question id=0 with type='passage'.\n"
            "  Then generate questions ABOUT THAT PASSAGE.\n"
            "- For mcq questions, provide exactly 4 options labelled A, B, C, D.\n"
            "- For true_false questions, options should be [\"True\", \"False\"].\n"
            "- For short_answer questions, set options to null.\n"
        )
    elif test_mode == "set_texts":
        set_texts = hkdse.get_set_texts_list()
        type_rules = (
            "- This is a 十二篇範文 (Set Texts) test for HKDSE Chinese.\n"
            f"- The topic/text being tested: {topic}\n"
            "- Include a MIX: some mcq, mostly short_answer that require textual analysis.\n"
            "- For mcq questions, provide exactly 4 options.\n"
            "- For short_answer questions, set options to null. Answers should demonstrate understanding of the text.\n"
            "- Questions should test: 語譯 (translation), 修辭 (rhetoric), 主旨理解 (theme comprehension), "
            "content recall, and analytical skills.\n"
            "- Use question patterns like:\n"
        )
        for pattern in hkdse.SUBJECT_KNOWLEDGE.get("Chinese", {}).get("set_texts_question_patterns", []):
            type_rules += f"  · {pattern}\n"
    else:
        # standard mix
        type_rules = (
            "- Include a MIX of question types: multiple choice (mcq), true/false (true_false), and short answer (short_answer).\n"
            "- For mcq questions, provide exactly 4 options labelled A, B, C, D.\n"
            "- For true_false questions, options should be [\"True\", \"False\"].\n"
            "- For short_answer questions, set options to null. These are open-ended conceptual questions and will be graded out of 2 marks.\n"
        )

    if type_mix:
        mix_str = ", ".join(f"{int(v*100)}% {k}" for k, v in type_mix.items() if v > 0)
        type_rules += f"- Aim for roughly this distribution: {mix_str}.\n"

    # ── Exemplar block ────────────────────────────────────────────────
    exemplar_block = ""
    if exemplars:
        exemplar_block = "\n--- EXAMPLE QUESTION PATTERNS (follow this style) ---\n"
        for ex in exemplars[:3]:
            exemplar_block += f"\n{ex}\n"
        exemplar_block += "\n--- END EXAMPLES ---\n"

    # ── Reading-specific: exemplar stems ──────────────────────────────
    if test_mode == "reading":
        reading_exemplars = subj_knowledge.get("reading_exemplar_stems", [])
        if reading_exemplars:
            exemplar_block = "\n--- EXAMPLE READING TEST PATTERNS ---\n"
            for ex in reading_exemplars[:2]:
                exemplar_block += f"\n{ex}\n"
            exemplar_block += "\n--- END EXAMPLES ---\n"

    prompt = (
        f"Generate exactly {num_questions} quiz questions for a Hong Kong secondary school student.\n\n"
        f"Subject: {subject}\n"
        f"Topic: {topic}\n"
        f"Test mode: {test_mode}\n"
        f"Difficulty: {difficulty}\n"
        f"Student class level: {class_level} (Form {form_number})\n\n"
        f"=== HKDSE / HK SCHOOL EXAM STYLE GUIDE ===\n{style_guide}\n\n"
        f"=== FORM-LEVEL DIFFICULTY ===\n{diff_text}\n\n"
        f"{exemplar_block}\n"
        f"=== MARKING NOTES ===\n{marking_notes}\n\n"
        "Rules:\n"
        f"{type_rules}"
        "- Each question must have exactly ONE correct answer.\n"
        "- For short_answer questions, correct_answer should contain the essential idea(s) required for full credit.\n"
        "- Provide a short explanation (1-2 sentences) for each question.\n"
        "- Provide a helpful hint for each question.\n"
        "- Use clear language appropriate for the form level.\n"
        "- Math expressions: use \\\\(...\\\\) for inline and \\\\[...\\\\] for display math. Do NOT use dollar signs.\n"
        "- Questions MUST closely match the style, format, and difficulty of real HKDSE exams or HK school internal exams for this form level.\n\n"
        "Return ONLY a valid JSON array. No markdown fences, no extra text.\n"
        "Each element must have these exact keys:\n"
        '  id (int), type ("mcq"|"true_false"|"short_answer"|"passage"), question (string), '
        "options (array of strings or null), correct_answer (string), explanation (string), hint (string)\n"
    )

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(temperature=0.7),
            )
            raw = (response.text or "").strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            try:
                questions = json.loads(raw)
            except json.JSONDecodeError:
                # Fix invalid backslash escapes from LaTeX math like \( \) \[ \] \angle
                raw = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
                questions = json.loads(raw)
            if isinstance(questions, list) and len(questions) > 0:
                for i, q in enumerate(questions):
                    q["id"] = i + 1
                    if q.get("type") not in ("mcq", "true_false", "short_answer", "passage"):
                        q["type"] = "mcq"
                    if not q.get("question"):
                        continue
                    if not q.get("correct_answer"):
                        q["correct_answer"] = ""
                    if not q.get("explanation"):
                        q["explanation"] = ""
                    if not q.get("hint"):
                        q["hint"] = ""
                return questions
        except Exception:
            if attempt < 2:
                time.sleep(1)
                continue
            break

    return []


# ─── Writing assessment ──────────────────────────────────────────────────

def generate_writing_prompt(
    *,
    client: Any,
    types: Any,
    model_name: str,
    subject: str,
    topic: str,
    class_level: str,
    difficulty: str,
    is_self_typed: bool = False,
) -> dict[str, Any]:
    """Generate a single writing prompt appropriate for the student's level.

    Returns {"prompt": "...", "genre": "...", "word_limit": "...", "instructions": "..."}
    """
    form_number = 4
    m = re.match(r"(?:F|FORM)?\s*(\d+)", (class_level or "").strip(), re.IGNORECASE)
    if m:
        form_number = int(m.group(1))

    word_target = "650字" if (subject == "Chinese" and form_number >= 4) else (
        "300字" if subject == "Chinese" else (
            "400 words" if form_number >= 4 else "150 words"
        )
    )

    if is_self_typed:
        return {
            "prompt": topic,
            "genre": "自訂題目" if subject == "Chinese" else "Custom Topic",
            "word_limit": word_target,
            "instructions": "請根據以上自訂題目撰寫文章。" if subject == "Chinese" else "Please write based on your custom topic."
        }

    form_desc = hkdse.get_form_descriptor(form_number)
    subj_knowledge = hkdse.get_subject_knowledge(subject)
    bucket = "senior" if form_number >= 4 else "junior"
    sample_prompts = subj_knowledge.get("writing_prompts_by_form", {}).get(bucket, [])

    sample_block = ""
    if sample_prompts:
        sample_block = "Here are some example prompts for reference (generate a NEW one, do not copy):\n"
        for sp in sample_prompts[:3]:
            sample_block += f"  - {sp}\n"

    lang = "Chinese" if subject == "Chinese" else "English"

    topic_instruction = ""
    if topic:
        topic_instruction = (
            f"The writing task must be clearly based on this selected topic/theme: {topic}.\n"
            "Do not ignore the topic. The prompt, scenario, and task purpose must align with it.\n"
        )

    prompt = (
        f"Generate a single writing prompt for an HKDSE-style {lang} writing test.\n\n"
        f"Selected topic/theme: {topic or 'General Writing'}\n"
        f"Student: Form {form_number}, difficulty={difficulty}\n"
        f"{form_desc}\n\n"
        f"{sample_block}\n"
        f"{topic_instruction}"
        f"The prompt should be appropriate for Form {form_number} and suitable for the HKDSE {lang} Paper 2 style.\n"
        f"Target length for student: approximately {word_target}.\n\n"
        "Return ONLY valid JSON with these keys:\n"
        '{"prompt": "the writing task instruction", "genre": "article/letter/speech/blog/story/essay", '
        f'"word_limit": "{word_target}", "instructions": "any additional instructions for the student"'
        "}\n"
    )

    if not client or not types:
        # Fallback: use a sample prompt
        import random
        if sample_prompts:
            chosen = random.choice(sample_prompts)
            themed_prompt = f"{chosen}\n\nTheme focus: {topic}" if topic else chosen
            return {"prompt": themed_prompt, "genre": "essay", "word_limit": word_target, "instructions": ""}
        fallback_prompt = f"Write an essay based on the theme '{topic}'. ({word_target})" if topic else f"Write an essay on a topic of your choice. ({word_target})"
        return {"prompt": fallback_prompt, "genre": "essay", "word_limit": word_target, "instructions": ""}

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(temperature=0.8),
            )
            raw = (response.text or "").strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("prompt"):
                return parsed
        except Exception:
            if attempt == 0:
                time.sleep(0.5)
                continue
            break

    import random
    if sample_prompts:
        chosen = random.choice(sample_prompts)
        themed_prompt = f"{chosen}\n\nTheme focus: {topic}" if topic else chosen
        return {"prompt": themed_prompt, "genre": "essay", "word_limit": word_target, "instructions": ""}
    fallback_prompt = f"Write an essay based on the theme '{topic}'. ({word_target})" if topic else f"Write an essay. ({word_target})"
    return {"prompt": fallback_prompt, "genre": "essay", "word_limit": word_target, "instructions": ""}


def grade_writing(
    *,
    client: Any,
    types: Any,
    model_name: str,
    subject: str,
    class_level: str,
    writing_prompt: str,
    student_text: str,
) -> dict[str, Any]:
    """Grade a student's writing using the HKDSE rubric.

    Returns a dict with the complete grading feedback as structured data.
    """
    normalized_subject = (subject or "").strip()

    if normalized_subject == "Chinese":
        rubric = hkdse.CHINESE_WRITING_RUBRIC
    elif normalized_subject == "English":
        rubric = hkdse.ENGLISH_WRITING_RUBRIC
    else:
        rubric = hkdse.get_writing_rubric(normalized_subject)

    if not rubric:
        return {"error": "No writing rubric available for this subject."}

    form_number = 4
    m_match = re.match(r"(?:F|FORM)?\s*(\d+)", (class_level or "").strip(), re.IGNORECASE)
    if m_match:
        form_number = int(m_match.group(1))

    form_desc = hkdse.get_form_descriptor(form_number)

    if normalized_subject == "Chinese":
        prompt = (
            f"{rubric}\n\n"
            f"科目：中國語文\n"
            f"學生就讀中{form_number}。\n"
            f"{form_desc}\n\n"
            f"寫作題目：\n{writing_prompt}\n\n"
            f"學生作文：\n{student_text}\n\n"
            "你是HKDSE中國語文卷二閱卷員。這是打字提交的作文，不是手寫稿。\n"
            "請嚴格按照上方的中文評分準則評核此文，但必須完全忽略錯別字扣分規則，不可因打字用字、輸入法選字或別字另行扣分。\n"
            "只按內容、表達、結構、標點字體四項評分。四項合計必須為100分。\n"
            "所有評語、優點、建議必須以繁體中文撰寫。\n"
            "Return your assessment as valid JSON with exactly these keys:\n"
            "{\n"
            '  "level": "Level 2|3|4|5|5*",\n'
            '  "score": 0-100,\n'
            '  "detailed_scores": {"content": X, "expression": X, "structure": X, "punctuation": X},\n'
            '  "overall_comment": "150-200字整體評語（繁體中文）",\n'
            '  "strengths": ["優點1", "優點2"],\n'
            '  "improvements": ["改善建議1", "改善建議2"],\n'
            '  "suggestions": ["提升方法1", "提升方法2"],\n'
            '  "level_ceiling": "解釋為何未達更高等級（繁體中文）",\n'
            '  "sample_paragraph": "示範段落（繁體中文）"\n'
            "}\n\n"
            "Return ONLY valid JSON. No markdown fences."
        )
    else:
        prompt = (
            f"{rubric}\n\n"
            f"Subject: English Language\n"
            f"Student is Form {form_number}.\n"
            f"{form_desc}\n\n"
            f"Writing Task:\n{writing_prompt}\n\n"
            f"Student's Essay:\n{student_text}\n\n"
            "You are an HKDSE English Paper 2 examiner. Assess using ONLY the English rubric above "
            "(Content/Language/Organization bands 1-7). Write all feedback in English.\n"
            "Return your assessment as valid JSON with exactly these keys:\n"
            "{\n"
            '  "level": "Level 2|3|4|5|5*",\n'
            '  "score": 0-100,\n'
            '  "band_scores": {"content": X, "language": X, "organization": X},\n'
            '  "overall_comment": "150-200 word overall assessment",\n'
            '  "strengths": ["strength 1", "strength 2"],\n'
            '  "improvements": ["improvement 1", "improvement 2"],\n'
            '  "suggestions": ["suggestion 1", "suggestion 2"],\n'
            '  "level_ceiling": "Explanation of why not one level higher",\n'
            '  "sample_paragraph": "A rewritten Band 7 sample paragraph"\n'
            "}\n\n"
            "Return ONLY valid JSON. No markdown fences."
        )

    if not client or not types:
        return {"error": "AI client not available."}

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(temperature=0.3),
            )
            raw = (response.text or "").strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                if normalized_subject == "Chinese":
                    detailed_scores = parsed.get("detailed_scores")
                    if isinstance(detailed_scores, dict):
                        detailed_scores.pop("typo_bonus", None)
                return parsed
        except Exception:
            if attempt == 0:
                time.sleep(1)
                continue
            break

    return {"error": "Failed to grade writing. Please try again."}
