"""HKDSE Mathematics (Compulsory Part) subject knowledge."""

MATH_KNOWLEDGE = {
    "test_modes": ["mc_only"],
    "style_guide": (
        "Follow the HKDSE Mathematics (Compulsory Part) exam style.\n"
        "Paper 2 is ALL multiple choice (45 questions, 4 options A/B/C/D).\n"
        "For this quiz, generate MC questions only.\n"
        "Questions should be calculation-based and follow DSE conventions:\n"
        "- Q1-Q15: straightforward computation (Number & Algebra, Measures/Shape/Space)\n"
        "- Q16-Q30: moderate difficulty, requiring 2-3 steps\n"
        "- Q31-Q45: harder questions, multi-step, includes statistics & probability\n\n"
        "For junior forms (F1-F3), follow the junior secondary maths curriculum:\n"
        "  F1: integers, fractions, decimals, basic algebra, area/perimeter, angles\n"
        "  F2: linear equations, percentages, Pythagoras, coordinate geometry, statistics\n"
        "  F3: indices, polynomials, trigonometry basics, probability, similar figures\n\n"
        "Use \\\\(...\\\\) for inline math and \\\\[...\\\\] for display math."
    ),
    "topics_by_form": {
        "1": ["Integers & operations", "Fractions & decimals", "Basic algebra", "Area & perimeter", "Angles & triangles", "Data handling"],
        "2": ["Linear equations", "Percentages & ratios", "Pythagoras theorem", "Coordinate geometry", "Statistics basics", "Formulas & substitution"],
        "3": ["Indices & surds", "Polynomials", "Basic trigonometry", "Probability", "Similar figures", "Congruent triangles", "Linear inequalities"],
        "4": ["Quadratic equations", "Functions & graphs", "Exponential & logarithms", "Trigonometry", "Coordinate geometry of circles", "Permutations & combinations", "Statistics"],
        "5": ["Sequences & series", "Inequalities (quadratic)", "More trigonometry", "Equation of circles", "Probability (advanced)", "Measures of dispersion"],
        "6": ["DSE Paper 2 full range", "Number systems review", "Algebra review", "Geometry review", "Statistics & probability review"],
    },
    "exemplar_stems": [
        "If \\\\(x + 3 = 7\\\\), then \\\\(x =\\\\)\nA. 3\nB. 4\nC. 7\nD. 10",
        "The mean of 5 numbers is 8. If one number is removed and the mean becomes 7, what is the removed number?\nA. 11\nB. 12\nC. 13\nD. 15",
        "In the figure, ABCD is a parallelogram. If \\\\(\\angle ABC = 110°\\\\), find \\\\(\\angle ADC\\\\).\nA. 70°\nB. 90°\nC. 110°\nD. 120°",
    ],
    "marking_notes": {
        "mc_only": "All MC. 1 mark per question. 4 options (A/B/C/D). No penalty for wrong answers."
    },
    "question_type_mix": {
        "mc_only": {"mcq": 1.0},
    },
}
