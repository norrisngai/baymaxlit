"""HKDSE Chinese History (中國歷史) subject knowledge."""

CHINESE_HISTORY_KNOWLEDGE = {
    "test_modes": ["standard"],
    "style_guide": (
        "遵循HKDSE中國歷史科考試風格。\n"
        "卷一：歷代發展（選答）\n"
        "卷二：歷史專題\n"
        "題型包括：選擇題、資料題、論述題。\n"
        "考試強調史實分析、因果關係、歷史評價。\n"
        "For quiz: mix MC, T/F, and short answer.\n"
        "MC should test historical facts and cause-effect relationships.\n"
        "Short answers should require brief analysis with historical evidence."
    ),
    "exemplar_stems": [
        "（選擇題）秦始皇統一六國後推行的制度不包括以下哪一項？\n"
        "A. 郡縣制\nB. 書同文\nC. 科舉制\nD. 車同軌",
    ],
    "marking_notes": {"standard": "MC: 1 mark. Short answer: 2 marks. T/F: 1 mark."},
    "question_type_mix": {"standard": {"mcq": 0.35, "true_false": 0.10, "short_answer": 0.55}},
}
