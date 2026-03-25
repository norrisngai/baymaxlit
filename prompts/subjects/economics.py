"""HKDSE Economics subject knowledge."""

ECONOMICS_KNOWLEDGE = {
    "test_modes": ["standard"],
    "style_guide": (
        "Follow the HKDSE Economics exam style.\n"
        "Paper 1: MC (45 questions)\n"
        "Paper 2: structured/essay questions with data response\n"
        "For quiz: mix MC, T/F, and short-answer.\n"
        "MC should test economic concepts, definitions, and simple graphical analysis.\n"
        "Short answers should require brief explanation with economic reasoning.\n"
        "Include some questions with HK economic context."
    ),
    "exemplar_stems": [
        "(MC) When the price of a normal good rises, the quantity demanded\nA. increases\nB. decreases\nC. remains unchanged\nD. cannot be determined",
    ],
    "marking_notes": {"standard": "MC: 1 mark. Short answer: 2 marks. T/F: 1 mark."},
    "question_type_mix": {"standard": {"mcq": 0.45, "true_false": 0.10, "short_answer": 0.45}},
}
