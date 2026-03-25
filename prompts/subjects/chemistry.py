"""HKDSE Chemistry subject knowledge."""

CHEMISTRY_KNOWLEDGE = {
    "test_modes": ["standard"],
    "style_guide": (
        "Follow the HKDSE Chemistry exam style.\n"
        "Paper 1: MC (36 questions) – concept recall, calculations, data interpretation\n"
        "Paper 2: structured questions – require chemical equations, calculations, explanations\n"
        "For quiz: mix MC, T/F, and short-answer.\n"
        "MC questions should test concept understanding and simple calculations.\n"
        "Short answers should require brief explanation or balanced equations.\n"
        "Use proper chemical notation, formulae, and units."
    ),
    "exemplar_stems": [
        "(MC) Which of the following is an ionic compound?\nA. CO₂\nB. NaCl\nC. CH₄\nD. H₂O",
        "(Short answer) Write a balanced equation for the reaction between magnesium and hydrochloric acid.",
    ],
    "marking_notes": {"standard": "MC: 1 mark. Short answer: 2 marks. T/F: 1 mark."},
    "question_type_mix": {"standard": {"mcq": 0.45, "true_false": 0.10, "short_answer": 0.45}},
}
