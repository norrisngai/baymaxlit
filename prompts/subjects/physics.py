"""HKDSE Physics subject knowledge."""

PHYSICS_KNOWLEDGE = {
    "test_modes": ["standard"],
    "style_guide": (
        "Follow the HKDSE Physics exam style.\n"
        "Paper 1: MC (36 questions) – test concepts, formulae, and data interpretation\n"
        "Paper 2: structured & long questions – require working, diagrams, explanations\n"
        "For quiz: mix MC, T/F, and short-answer questions.\n"
        "MC should test conceptual understanding and formula application.\n"
        "Short answers should require brief calculations or explanations (2-3 lines).\n"
        "Use proper SI units. Provide reasonable numerical values.\n"
        "Use \\\\(...\\\\) for inline math.\n\n"
        "For junior forms (F1-F3): Integrated Science level. "
        "Focus on observation, simple experiments, basic concepts."
    ),
    "exemplar_stems": [
        "(MC) A ball is thrown vertically upward. At the highest point, its velocity is\nA. maximum\nB. zero\nC. equal to initial velocity\nD. negative",
        "(Short answer) A 2 kg block is pushed with a force of 10 N on a frictionless surface. Calculate the acceleration.",
    ],
    "marking_notes": {"standard": "MC: 1 mark. Short answer: 2 marks (1 for method, 1 for answer). T/F: 1 mark."},
    "question_type_mix": {"standard": {"mcq": 0.45, "true_false": 0.10, "short_answer": 0.45}},
}
