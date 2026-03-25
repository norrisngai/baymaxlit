"""HKDSE Geography subject knowledge."""

GEOGRAPHY_KNOWLEDGE = {
    "test_modes": ["standard"],
    "style_guide": (
        "Follow the HKDSE Geography exam style.\n"
        "Paper 1: structured data-response questions with maps, photos, data tables\n"
        "Paper 2: fieldwork-based questions\n"
        "For quiz: mix MC, T/F, and short-answer.\n"
        "MC should test geographical concepts, map skills, and data interpretation.\n"
        "Short answers should require brief explanation with geographical reasoning.\n"
        "Include HK-specific examples where possible."
    ),
    "exemplar_stems": [
        "(MC) Which of the following is a push factor for rural-urban migration?\nA. Better job opportunities in cities\nB. Higher wages in cities\nC. Crop failure in rural areas\nD. Better healthcare in cities",
    ],
    "marking_notes": {"standard": "MC: 1 mark. Short answer: 2 marks. T/F: 1 mark."},
    "question_type_mix": {"standard": {"mcq": 0.40, "true_false": 0.10, "short_answer": 0.50}},
}
