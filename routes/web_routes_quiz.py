"""Quiz routes for student quiz feature."""

from __future__ import annotations

import json
from typing import Any

from flask import Flask, jsonify, render_template, request, current_app

import web_context
import web_db
import web_quiz
import web_hkdse_knowledge as hkdse
from web_constants import CORE_SUBJECT_CHOICES, ELECTIVE_SUBJECT_CHOICES


# ── Topic map (electives + core subjects) ─────────────────────────────────

TOPICS_BY_SUBJECT: dict[str, dict[str, list[str]]] = {
    # ── Core subjects ─────────────────────────────────────────────────
    "English": {
        "1": ["Reading Comprehension", "Vocabulary & Grammar", "Tenses", "Parts of Speech", "Simple Writing"],
        "2": ["Reading Comprehension", "Vocabulary & Grammar", "Sentence Structures", "Writing (Letters & Emails)", "Tenses (Advanced)"],
        "3": ["Reading Comprehension", "Vocabulary & Grammar", "Writing (Articles & Stories)", "Idioms & Phrases", "Comprehension Cloze"],
        "4": ["Social Issues & Contemporary Life", "Popular Culture & Media", "Workplace Communication & Proposals", "Science & Technology", "Literature, Drama & Media Studies", "Moral/Civic Education & National Identity"],
        "5": ["Social Issues & Contemporary Life", "Popular Culture & Media", "Workplace Communication & Proposals", "Science & Technology", "Literature, Drama & Media Studies", "Moral/Civic Education & National Identity"],
        "6": ["Social Issues & Contemporary Life", "Popular Culture & Media", "Workplace Communication & Proposals", "Science & Technology", "Literature, Drama & Media Studies", "Moral/Civic Education & National Identity"],
    },
    "Chinese": {
        "1": ["閱讀理解", "語文基礎知識", "詞語運用", "句式", "簡單寫作"],
        "2": ["閱讀理解", "語文基礎知識", "修辭手法", "文言文入門", "寫作（記敘文）"],
        "3": ["閱讀理解", "語文基礎知識", "文言文", "修辭與寫作手法", "寫作（記敘文/描寫文）"],
        "4": ["閱讀理解（卷一）", "寫作能力（卷二）", "十二篇範文", "文言文閱讀", "語文運用"],
        "5": ["閱讀理解（卷一）", "寫作能力（卷二）", "十二篇範文", "文言文閱讀", "語文運用"],
        "6": ["閱讀理解（卷一）", "寫作能力（卷二）", "十二篇範文", "文言文閱讀", "語文運用"],
    },
    "Math": {
        "1": ["Integers & operations", "Fractions & decimals", "Basic algebra", "Area & perimeter", "Angles & triangles", "Data handling"],
        "2": ["Linear equations", "Percentages & ratios", "Pythagoras theorem", "Coordinate geometry", "Statistics basics", "Formulas & substitution"],
        "3": ["Indices & surds", "Polynomials", "Basic trigonometry", "Probability", "Similar figures", "Congruent triangles", "Linear inequalities"],
        "4": ["Quadratic equations", "Functions & graphs", "Exponential & logarithms", "Trigonometry", "Coordinate geometry of circles", "Permutations & combinations", "Statistics"],
        "5": ["Sequences & series", "Inequalities (quadratic)", "More trigonometry", "Equation of circles", "Probability (advanced)", "Measures of dispersion"],
        "6": ["DSE Paper 2 full range", "Number systems review", "Algebra review", "Geometry review", "Statistics & probability review"],
    },
    # ── Elective subjects ─────────────────────────────────────────────
    "Phy": {
        "1": ["Scientific Investigation", "Energy", "Matter", "Electricity", "Forces and Motion", "Space Science", "Light and Sound", "Light and Colour"],
        "2": ["Scientific Investigation", "Energy", "Matter", "Electricity", "Forces and Motion", "Space Science", "Light and Sound", "Light and Colour"],
        "3": ["Scientific Investigation", "Energy", "Heat and Gases", "Electricity and Magnetism", "Force and Motion", "Astronomy and Space Science", "Wave Motion", "Medical Physics"],
        "4": ["Force and Motion", "Work, Energy and Power", "Thermal Physics", "Electricity", "Waves", "Radioactivity"],
        "5": ["Force and Motion (Advanced)", "Heat and Gases", "Wave Motion (excluding Light)", "Electricity and Magnetism"],
        "6": ["Wave Motion (Light)", "Atomic Physics", "Nuclear Physics", "Medical Physics", "Astronomy and Space Science"],
    },
    "Chem": {
        "4": ["Atomic structure & periodicity", "Bonding & structure", "Mole concept & stoichiometry", "Gases & gas laws", "Energetics", "Chemical kinetics", "Chemical equilibrium", "Acids & bases", "Redox & electrochemistry", "Organic chemistry (functional groups)", "Polymers & materials", "Analytical chemistry (basic)"],
        "5": ["Atomic structure & periodicity", "Bonding & structure", "Mole concept & stoichiometry", "Gases & gas laws", "Energetics", "Chemical kinetics", "Chemical equilibrium", "Acids & bases", "Redox & electrochemistry", "Organic chemistry (functional groups)", "Polymers & materials", "Analytical chemistry (basic)"],
        "6": ["Atomic structure & periodicity", "Bonding & structure", "Mole concept & stoichiometry", "Gases & gas laws", "Energetics", "Chemical kinetics", "Chemical equilibrium", "Acids & bases", "Redox & electrochemistry", "Organic chemistry (functional groups)", "Polymers & materials", "Analytical chemistry (basic)"],
    },
    "Bio": {
        "4": ["Cells & organisation", "Biomolecules & enzymes", "Nutrition & digestion", "Gas exchange & transport", "Respiration & photosynthesis", "Homeostasis & regulation", "Coordination (nervous/endocrine)", "Reproduction & development", "Genetics & inheritance", "Evolution & biodiversity", "Ecology & conservation", "Health, microbes & immunity"],
        "5": ["Cells & organisation", "Biomolecules & enzymes", "Nutrition & digestion", "Gas exchange & transport", "Respiration & photosynthesis", "Homeostasis & regulation", "Coordination (nervous/endocrine)", "Reproduction & development", "Genetics & inheritance", "Evolution & biodiversity", "Ecology & conservation", "Health, microbes & immunity"],
        "6": ["Cells & organisation", "Biomolecules & enzymes", "Nutrition & digestion", "Gas exchange & transport", "Respiration & photosynthesis", "Homeostasis & regulation", "Coordination (nervous/endocrine)", "Reproduction & development", "Genetics & inheritance", "Evolution & biodiversity", "Ecology & conservation", "Health, microbes & immunity"],
    },
    "M1": {
        "4": ["Functions & graphs (advanced)", "Limits & differentiation", "Applications of differentiation", "Integration basics", "Applications of integration", "Probability basics", "Distributions (binomial/normal)", "Statistics & inference (basic)", "Regression & correlation"],
        "5": ["Functions & graphs (advanced)", "Limits & differentiation", "Applications of differentiation", "Integration basics", "Applications of integration", "Probability basics", "Distributions (binomial/normal)", "Statistics & inference (basic)", "Regression & correlation"],
        "6": ["Functions & graphs (advanced)", "Limits & differentiation", "Applications of differentiation", "Integration basics", "Applications of integration", "Probability basics", "Distributions (binomial/normal)", "Statistics & inference (basic)", "Regression & correlation"],
    },
    "M2": {
        "4": ["Functions & transformations", "Sequences & series", "Exponential & logarithmic functions", "Trigonometry (functions & identities)", "Differentiation (advanced)", "Integration (advanced)", "Vectors (2D/3D basics)", "Matrices & linear systems (basic)", "Complex numbers (basic)"],
        "5": ["Functions & transformations", "Sequences & series", "Exponential & logarithmic functions", "Trigonometry (functions & identities)", "Differentiation (advanced)", "Integration (advanced)", "Vectors (2D/3D basics)", "Matrices & linear systems (basic)", "Complex numbers (basic)"],
        "6": ["Functions & transformations", "Sequences & series", "Exponential & logarithmic functions", "Trigonometry (functions & identities)", "Differentiation (advanced)", "Integration (advanced)", "Vectors (2D/3D basics)", "Matrices & linear systems (basic)", "Complex numbers (basic)"],
    },
    "Geog": {
        "4": ["Map skills & spatial data", "Weather & climate", "River & slope processes", "Coastal processes & management", "Natural hazards & risk management", "Urban environments & planning", "Population change & migration", "Economic development & globalisation", "Resource management (water/energy/food)", "Sustainable development"],
        "5": ["Map skills & spatial data", "Weather & climate", "River & slope processes", "Coastal processes & management", "Natural hazards & risk management", "Urban environments & planning", "Population change & migration", "Economic development & globalisation", "Resource management (water/energy/food)", "Sustainable development"],
        "6": ["Map skills & spatial data", "Weather & climate", "River & slope processes", "Coastal processes & management", "Natural hazards & risk management", "Urban environments & planning", "Population change & migration", "Economic development & globalisation", "Resource management (water/energy/food)", "Sustainable development"],
    },
    "Econ": {
        "4": ["Basic economic concepts", "Demand, supply & elasticity", "Firms: production, cost & revenue", "Market structures & competition", "Market failure & government intervention", "National income & indicators", "Fiscal & monetary policy", "Inflation, unemployment & growth", "International trade", "Exchange rates & balance of payments"],
        "5": ["Basic economic concepts", "Demand, supply & elasticity", "Firms: production, cost & revenue", "Market structures & competition", "Market failure & government intervention", "National income & indicators", "Fiscal & monetary policy", "Inflation, unemployment & growth", "International trade", "Exchange rates & balance of payments"],
        "6": ["Basic economic concepts", "Demand, supply & elasticity", "Firms: production, cost & revenue", "Market structures & competition", "Market failure & government intervention", "National income & indicators", "Fiscal & monetary policy", "Inflation, unemployment & growth", "International trade", "Exchange rates & balance of payments"],
    },
    "BAFS": {
        "4": ["Business ownership & entrepreneurship", "Business environment (HK & global)", "Management & decision making", "Marketing basics", "Operations & human resources", "Business ethics & social responsibility", "Accounting basics (equation & double entry)", "Financial statements (P/L, B/S, cash flow)", "Costing & break-even", "Budgeting (basic)", "Financial analysis (ratios)", "Internal control (basic)"],
        "5": ["Business ownership & entrepreneurship", "Business environment (HK & global)", "Management & decision making", "Marketing basics", "Operations & human resources", "Business ethics & social responsibility", "Accounting basics (equation & double entry)", "Financial statements (P/L, B/S, cash flow)", "Costing & break-even", "Budgeting (basic)", "Financial analysis (ratios)", "Internal control (basic)"],
        "6": ["Business ownership & entrepreneurship", "Business environment (HK & global)", "Management & decision making", "Marketing basics", "Operations & human resources", "Business ethics & social responsibility", "Accounting basics (equation & double entry)", "Financial statements (P/L, B/S, cash flow)", "Costing & break-even", "Budgeting (basic)", "Financial analysis (ratios)", "Internal control (basic)"],
    },
    "Chinese History": {
        "4": ["Early imperial China (Qin–Han)", "Tang–Song: governance & culture", "Yuan–Ming–Qing: rule & society", "Late Qing reforms & crises", "Republican China (1911–1949)", "Modern China (1949–present)", "China and foreign relations", "Social & economic changes", "Culture, thought & institutions"],
        "5": ["Early imperial China (Qin–Han)", "Tang–Song: governance & culture", "Yuan–Ming–Qing: rule & society", "Late Qing reforms & crises", "Republican China (1911–1949)", "Modern China (1949–present)", "China and foreign relations", "Social & economic changes", "Culture, thought & institutions"],
        "6": ["Early imperial China (Qin–Han)", "Tang–Song: governance & culture", "Yuan–Ming–Qing: rule & society", "Late Qing reforms & crises", "Republican China (1911–1949)", "Modern China (1949–present)", "China and foreign relations", "Social & economic changes", "Culture, thought & institutions"],
    },
    "History": {
        "4": ["Industrialisation & imperialism", "World War I & peace settlements", "Interwar period & rise of totalitarianism", "World War II (Europe & Asia)", "Cold War: origins & key crises", "Decolonisation & nationalism", "International relations since 1991", "Historical skills (source analysis)", "Historical writing (essay skills)"],
        "5": ["Industrialisation & imperialism", "World War I & peace settlements", "Interwar period & rise of totalitarianism", "World War II (Europe & Asia)", "Cold War: origins & key crises", "Decolonisation & nationalism", "International relations since 1991", "Historical skills (source analysis)", "Historical writing (essay skills)"],
        "6": ["Industrialisation & imperialism", "World War I & peace settlements", "Interwar period & rise of totalitarianism", "World War II (Europe & Asia)", "Cold War: origins & key crises", "Decolonisation & nationalism", "International relations since 1991", "Historical skills (source analysis)", "Historical writing (essay skills)"],
    },
}

# ── Test modes available per subject ──────────────────────────────────────
# These define what UI options appear in the quiz setup.
# "standard" = mixed MC/TF/short answer
# "reading"  = reading comprehension test
# "writing"  = writing assessment
# "set_texts" = 十二篇範文 (Chinese only)
# "mc_only"   = all MC (Math)

TEST_MODES_BY_SUBJECT: dict[str, list[dict[str, str]]] = {
    "English": [
        {"value": "reading", "label": "Reading Test"},
        {"value": "writing", "label": "Writing Test"},
    ],
    "Chinese": [
        {"value": "reading", "label": "閱讀測驗"},
        {"value": "writing", "label": "寫作測驗"},
        {"value": "set_texts", "label": "十二篇範文"},
    ],
    "Math": [
        {"value": "mc_only", "label": "MC Only (Paper 2 style)"},
    ],
}
# All other subjects default to standard mode (no selector shown).

# ── Chinese set texts as topic options ────────────────────────────────────
CHINESE_SET_TEXTS = hkdse.get_set_texts_list()

QUIZ_COIN_REWARD = 500
QUIZ_PASS_PERCENT = 70


def register(app: Flask) -> None:

    @app.route("/quiz")
    def quiz():
        user = web_context.role_required("student")
        electives = web_context.student_electives(user)
        form_number = web_context.student_form_from_class_level(user.get("class_level") or "")

        # Build the subject list: core subjects first, then electives
        subjects: list[str] = list(CORE_SUBJECT_CHOICES)

        for subj in ELECTIVE_SUBJECT_CHOICES:
            if subj in TOPICS_BY_SUBJECT and subj in electives:
                subjects.append(subj)

        # For forms 1-3, Phy is available as integrated science
        if "Phy" in TOPICS_BY_SUBJECT and form_number in (1, 2, 3) and "Phy" not in subjects:
            subjects.insert(0, "Phy")

        attempts = web_db.list_quiz_attempts(user_id=int(user["id"]), limit=20)
        coins = web_db.get_user_coins(user_id=int(user["id"]))

        return render_template(
            "quiz.html",
            subjects=subjects,
            topics_by_subject=TOPICS_BY_SUBJECT,
            test_modes_by_subject=TEST_MODES_BY_SUBJECT,
            chinese_set_texts=CHINESE_SET_TEXTS,
            form_number=str(form_number) if form_number else "4",
            attempts=attempts,
            coins=coins,
        )

    @app.route("/api/quiz/generate", methods=["POST"])
    def api_quiz_generate():
        user = web_context.role_required("student")
        data = request.get_json(silent=True) or {}
        subject = (data.get("subject") or "").strip()
        topic = (data.get("topic") or "").strip()
        difficulty = (data.get("difficulty") or "intermediate").strip().lower()
        test_mode = (data.get("test_mode") or "standard").strip().lower()
        write_source = (data.get("write_source") or "ai").strip().lower()

        if not subject or not topic:
            return jsonify({"ok": False, "error": "Subject and topic are required."}), 400
        if difficulty not in ("basic", "intermediate", "advanced"):
            return jsonify({"ok": False, "error": "Invalid difficulty level."}), 400
        if test_mode not in ("standard", "reading", "writing", "set_texts", "mc_only"):
            return jsonify({"ok": False, "error": "Invalid test mode."}), 400

        class_level = user.get("class_level") or ""

        # ── Writing mode: generate a prompt instead of quiz questions ──
        if test_mode == "writing":
            prompt_data = web_quiz.generate_writing_prompt(
                client=current_app.config.get("GEMINI_CLIENT"),
                types=current_app.config.get("GEMINI_TYPES"),
                model_name=current_app.config.get("GEMINI_MODEL_NAME"),
                subject=subject,
                topic=topic,
                class_level=class_level,
                difficulty=difficulty,
                is_self_typed=(write_source == "self")
            )
            quiz_id = web_db.create_quiz_attempt(
                user_id=int(user["id"]),
                subject=subject,
                topic=f"Writing: {topic}",
                difficulty=difficulty,
                questions_json=json.dumps({"mode": "writing", "prompt_data": prompt_data}, ensure_ascii=False),
            )
            return jsonify({"ok": True, "quiz_id": quiz_id, "mode": "writing", "prompt_data": prompt_data})

        # ── Standard / reading / set_texts / mc_only quiz ──
        questions = web_quiz.generate_quiz(
            client=current_app.config.get("GEMINI_CLIENT"),
            types=current_app.config.get("GEMINI_TYPES"),
            model_name=current_app.config.get("GEMINI_MODEL_NAME"),
            subject=subject,
            topic=topic,
            difficulty=difficulty,
            class_level=class_level,
            test_mode=test_mode,
        )

        if not questions:
            return jsonify({"ok": False, "error": "Failed to generate quiz. Please try again."}), 500

        quiz_id = web_db.create_quiz_attempt(
            user_id=int(user["id"]),
            subject=subject,
            topic=topic,
            difficulty=difficulty,
            questions_json=json.dumps(questions, ensure_ascii=False),
        )

        return jsonify({"ok": True, "quiz_id": quiz_id, "questions": questions})

    @app.route("/api/quiz/<int:quiz_id>/submit", methods=["POST"])
    def api_quiz_submit(quiz_id: int):
        user = web_context.role_required("student")
        attempt = web_db.get_quiz_attempt(quiz_id=quiz_id, user_id=int(user["id"]))
        if not attempt:
            return jsonify({"ok": False, "error": "Quiz not found."}), 404
        if attempt.get("completed_at"):
            return jsonify({"ok": False, "error": "Quiz already submitted."}), 400

        data = request.get_json(silent=True) or {}
        student_answers = data.get("answers") or {}

        questions = json.loads(attempt["questions_json"])
        total = sum(2 if (q.get("type") == "short_answer") else 1 for q in questions)
        score = 0
        results = []

        short_answer_items = []
        for q in questions:
            if q.get("type") != "short_answer":
                continue
            qid = str(q["id"])
            short_answer_items.append({
                "id": qid,
                "question": q.get("question", ""),
                "student_answer": (student_answers.get(qid) or "").strip(),
                "reference_answer": (q.get("correct_answer") or "").strip(),
                "explanation": (q.get("explanation") or "").strip(),
            })

        short_answer_grades = web_quiz.grade_short_answer_responses(
            client=current_app.config.get("GEMINI_CLIENT"),
            types=current_app.config.get("GEMINI_TYPES"),
            model_name=current_app.config.get("GEMINI_MODEL_NAME"),
            subject=str(attempt.get("subject") or ""),
            topic=str(attempt.get("topic") or ""),
            class_level=str(user.get("class_level") or ""),
            items=short_answer_items,
        )

        for q in questions:
            qid = str(q["id"])
            student_ans = (student_answers.get(qid) or "").strip()
            correct = (q.get("correct_answer") or "").strip()

            max_marks = 2 if q.get("type") == "short_answer" else 1
            marks_awarded = 0
            grading_comment = ""
            status = "wrong"

            if q.get("type") == "short_answer":
                graded = short_answer_grades.get(qid) or {"score": 0, "comment": "Your answer does not show the expected main idea."}
                try:
                    marks_awarded = int(graded.get("score") or 0)
                except Exception:
                    marks_awarded = 0
                marks_awarded = max(0, min(2, marks_awarded))
                grading_comment = str(graded.get("comment") or "").strip()
                if marks_awarded >= 2:
                    status = "correct"
                elif marks_awarded == 1:
                    status = "partial"
                else:
                    status = "wrong"
            else:
                is_correct = student_ans.lower() == correct.lower() if student_ans and correct else False
                if is_correct:
                    marks_awarded = 1
                    status = "correct"
                else:
                    status = "wrong"

            score += marks_awarded
            is_correct = marks_awarded == max_marks

            results.append({
                "id": q["id"],
                "question": q["question"],
                "type": q["type"],
                "options": q.get("options"),
                "student_answer": student_ans,
                "correct_answer": correct,
                "is_correct": is_correct,
                "status": status,
                "marks_awarded": marks_awarded,
                "max_marks": max_marks,
                "grading_comment": grading_comment,
                "explanation": q.get("explanation", ""),
                "hint": q.get("hint", ""),
            })

        # Coin reward
        coins_awarded = 0
        if total > 0 and (score / total * 100) >= QUIZ_PASS_PERCENT:
            coins_awarded = QUIZ_COIN_REWARD
            web_db.add_user_coins(
                user_id=int(user["id"]),
                delta=coins_awarded,
                reason="quiz_pass",
                meta={"quiz_id": quiz_id, "score": score, "total": total},
            )

        web_db.complete_quiz_attempt(
            quiz_id=quiz_id,
            user_id=int(user["id"]),
            answers_json=json.dumps({"answers": student_answers, "results": results}, ensure_ascii=False),
            score=score,
            total=total,
            coins_awarded=coins_awarded,
        )

        percent = round(score / total * 100) if total > 0 else 0

        return jsonify({
            "ok": True,
            "score": score,
            "total": total,
            "percent": percent,
            "coins_awarded": coins_awarded,
            "results": results,
        })

    @app.route("/api/quiz/<int:quiz_id>", methods=["GET"])
    def api_quiz_get(quiz_id: int):
        """Load a past quiz attempt (incomplete → questions, completed → results)."""
        user = web_context.role_required("student")
        attempt = web_db.get_quiz_attempt(quiz_id=quiz_id, user_id=int(user["id"]))
        if not attempt:
            return jsonify({"ok": False, "error": "Quiz not found."}), 404

        questions_raw = json.loads(attempt["questions_json"])

        # Detect writing mode (stored as dict with "mode":"writing")
        is_writing = isinstance(questions_raw, dict) and questions_raw.get("mode") == "writing"

        if attempt.get("completed_at"):
            total = int(attempt.get("total") or 0)
            score = int(attempt.get("score") or 0)
            percent = round(score / total * 100) if total > 0 else 0

            if is_writing:
                # For writing quizzes, answers_json stores {grading_result: {...}}
                grading = {}
                try:
                    payload = json.loads(attempt.get("answers_json") or "{}")
                    grading = payload.get("grading_result", payload.get("grading", {}))
                except Exception:
                    pass
                return jsonify({
                    "ok": True,
                    "is_completed": True,
                    "mode": "writing",
                    "subject": attempt.get("subject", ""),
                    "score": score,
                    "total": total,
                    "percent": percent,
                    "coins_awarded": int(attempt.get("coins_awarded") or 0),
                    "grading": grading,
                })

            # Standard quiz
            questions = questions_raw if isinstance(questions_raw, list) else []
            student_answers = {}
            stored_results = None
            try:
                payload = json.loads(attempt.get("answers_json") or "{}")
                if isinstance(payload, dict) and isinstance(payload.get("answers"), dict):
                    student_answers = payload.get("answers") or {}
                    if isinstance(payload.get("results"), list):
                        stored_results = payload.get("results")
                elif isinstance(payload, dict):
                    student_answers = payload
            except Exception:
                pass

            if not total:
                total = len(questions)
            results = []
            if isinstance(stored_results, list) and stored_results:
                results = stored_results
            else:
                for q in questions:
                    qid = str(q["id"])
                    student_ans = (student_answers.get(qid) or "").strip()
                    correct = (q.get("correct_answer") or "").strip()
                    is_correct = student_ans.lower() == correct.lower() if student_ans and correct else False
                    results.append({
                        "id": q["id"],
                        "question": q["question"],
                        "type": q["type"],
                        "options": q.get("options"),
                        "student_answer": student_ans,
                        "correct_answer": correct,
                        "is_correct": is_correct,
                        "status": "correct" if is_correct else "wrong",
                        "marks_awarded": 1 if is_correct else 0,
                        "max_marks": 1,
                        "grading_comment": "",
                        "explanation": q.get("explanation", ""),
                        "hint": q.get("hint", ""),
                    })
            return jsonify({
                "ok": True,
                "is_completed": True,
                "score": score,
                "total": total,
                "percent": percent,
                "coins_awarded": int(attempt.get("coins_awarded") or 0),
                "results": results,
            })
        else:
            if is_writing:
                return jsonify({
                    "ok": True,
                    "is_completed": False,
                    "mode": "writing",
                    "quiz_id": quiz_id,
                    "subject": attempt["subject"],
                    "topic": attempt["topic"],
                    "difficulty": attempt["difficulty"],
                    "prompt_data": questions_raw.get("prompt_data", {}),
                })
            return jsonify({
                "ok": True,
                "is_completed": False,
                "quiz_id": quiz_id,
                "subject": attempt["subject"],
                "topic": attempt["topic"],
                "difficulty": attempt["difficulty"],
                "questions": questions_raw if isinstance(questions_raw, list) else [],
            })

    @app.route("/api/quiz/topics", methods=["GET"])
    def api_quiz_topics():
        """Return topics for a given subject + form, and test_mode."""
        web_context.role_required("student")
        subject = (request.args.get("subject") or "").strip()
        form = (request.args.get("form") or "4").strip()
        test_mode = (request.args.get("test_mode") or "standard").strip()

        # For Chinese set_texts mode, return the 12 set texts as topics
        if subject == "Chinese" and test_mode == "set_texts":
            return jsonify({"ok": True, "topics": CHINESE_SET_TEXTS})

        by_form = TOPICS_BY_SUBJECT.get(subject, {})
        topics = by_form.get(form, by_form.get("4", []))
        return jsonify({"ok": True, "topics": topics})

    # ── Writing submission endpoint ───────────────────────────────────
    @app.route("/api/quiz/<int:quiz_id>/submit-writing", methods=["POST"])
    def api_quiz_submit_writing(quiz_id: int):
        """Submit and grade a writing piece."""
        user = web_context.role_required("student")
        attempt = web_db.get_quiz_attempt(quiz_id=quiz_id, user_id=int(user["id"]))
        if not attempt:
            return jsonify({"ok": False, "error": "Quiz not found."}), 404
        if attempt.get("completed_at"):
            return jsonify({"ok": False, "error": "Already submitted."}), 400

        data = request.get_json(silent=True) or {}
        student_text = (data.get("text") or "").strip()
        if not student_text:
            return jsonify({"ok": False, "error": "Please write something before submitting."}), 400

        # Parse stored prompt data
        stored = json.loads(attempt.get("questions_json") or "{}")
        prompt_data = stored.get("prompt_data", {})
        writing_prompt = prompt_data.get("prompt", "")

        subject = attempt.get("subject") or ""
        # Remove "Writing: " prefix from topic for display
        class_level = user.get("class_level") or ""

        grading_result = web_quiz.grade_writing(
            client=current_app.config.get("GEMINI_CLIENT"),
            types=current_app.config.get("GEMINI_TYPES"),
            model_name=current_app.config.get("GEMINI_MODEL_NAME"),
            subject=subject,
            class_level=class_level,
            writing_prompt=writing_prompt,
            student_text=student_text,
        )

        if grading_result.get("error"):
            return jsonify({"ok": False, "error": grading_result["error"]}), 500

        # Compute score (0-100)
        score = int(grading_result.get("score", 0))
        total = 100

        # Coin reward for writing (same threshold)
        coins_awarded = 0
        if score >= QUIZ_PASS_PERCENT:
            coins_awarded = QUIZ_COIN_REWARD
            web_db.add_user_coins(
                user_id=int(user["id"]),
                delta=coins_awarded,
                reason="quiz_pass",
                meta={"quiz_id": quiz_id, "score": score, "total": total, "mode": "writing"},
            )

        web_db.complete_quiz_attempt(
            quiz_id=quiz_id,
            user_id=int(user["id"]),
            answers_json=json.dumps({
                "mode": "writing",
                "student_text": student_text,
                "grading_result": grading_result,
            }, ensure_ascii=False),
            score=score,
            total=total,
            coins_awarded=coins_awarded,
        )

        return jsonify({
            "ok": True,
            "mode": "writing",
            "subject": subject,
            "score": score,
            "total": total,
            "percent": score,
            "coins_awarded": coins_awarded,
            "grading": grading_result,
        })

    # ── Test modes API ────────────────────────────────────────────────
    @app.route("/api/quiz/test-modes", methods=["GET"])
    def api_quiz_test_modes():
        """Return available test modes for a subject."""
        web_context.role_required("student")
        subject = (request.args.get("subject") or "").strip()
        modes = TEST_MODES_BY_SUBJECT.get(subject, [])
        return jsonify({"ok": True, "modes": modes})
