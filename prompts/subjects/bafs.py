"""HKDSE BAFS (Business, Accounting and Financial Studies) subject knowledge."""

BAFS_KNOWLEDGE = {
    "test_modes": ["standard"],
    "style_guide": (
        "Follow the HKDSE BAFS exam style.\n"
        "Paper 1: MC + structured questions on business fundamentals\n"
        "Paper 2: elective module (Accounting / Management)\n"
        "For quiz: mix MC, T/F, and short-answer.\n"
        "MC should test business concepts and basic accounting principles.\n"
        "Short answers should require brief explanations with business reasoning."
    ),
    "exemplar_stems": [
        "(MC) Which of the following is a current asset?\nA. Land\nB. Cash\nC. Equipment\nD. Patent",
    ],
    "marking_notes": {"standard": "MC: 1 mark. Short answer: 2 marks. T/F: 1 mark."},
    "question_type_mix": {"standard": {"mcq": 0.40, "true_false": 0.15, "short_answer": 0.45}},
}
