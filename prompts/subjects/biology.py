"""HKDSE Biology subject knowledge."""

BIOLOGY_KNOWLEDGE = {
    "test_modes": ["standard"],
    "style_guide": (
        "Follow the HKDSE Biology exam style.\n"
        "Paper 1: MC (36 questions) – concept recall, diagram interpretation, data analysis\n"
        "Paper 2: structured questions – diagram labelling, data analysis, essay-type\n"
        "For quiz: mix MC, T/F, and short-answer.\n"
        "MC should include diagram-based and data interpretation questions.\n"
        "Short answers should test understanding of biological processes.\n"
        "Use proper biological terminology."
    ),
    "exemplar_stems": [
        "(MC) Which organelle is responsible for aerobic respiration?\nA. Nucleus\nB. Ribosome\nC. Mitochondrion\nD. Chloroplast",
        "(Short answer) Explain why the alveoli are well-suited for gas exchange. Give TWO features.",
    ],
    "marking_notes": {"standard": "MC: 1 mark. Short answer: 2 marks. T/F: 1 mark."},
    "question_type_mix": {"standard": {"mcq": 0.40, "true_false": 0.15, "short_answer": 0.45}},
}
