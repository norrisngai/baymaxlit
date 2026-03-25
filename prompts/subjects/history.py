"""HKDSE History subject knowledge."""

HISTORY_KNOWLEDGE = {
    "test_modes": ["standard"],
    "style_guide": (
        "Follow the HKDSE History exam style.\n"
        "Paper 1: document-based questions (DBQs) with source analysis\n"
        "Paper 2: essay questions on historical topics\n"
        "For quiz: mix MC, T/F, and short-answer.\n"
        "MC should test historical knowledge and source interpretation.\n"
        "Short answers should require analysis with evidence.\n"
        "Include source-based questions where appropriate."
    ),
    "exemplar_stems": [
        "(MC) The Treaty of Versailles (1919) required Germany to\nA. join the League of Nations immediately\nB. accept war guilt and pay reparations\nC. disarm its navy only\nD. return all its colonies to France",
    ],
    "marking_notes": {"standard": "MC: 1 mark. Short answer: 2 marks. T/F: 1 mark."},
    "question_type_mix": {"standard": {"mcq": 0.35, "true_false": 0.10, "short_answer": 0.55}},
}
