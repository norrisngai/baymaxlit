"""Form-level difficulty descriptors for HKDSE quiz generation."""

from __future__ import annotations


FORM_DIFFICULTY_DESCRIPTORS: dict[int, str] = {
    1: (
        "Form 1 (Secondary 1, ~age 12). Use simple, clear language. "
        "Questions should test basic recall and simple comprehension. "
        "Align with the Junior Secondary curriculum in Hong Kong. "
        "Vocabulary should be age-appropriate. "
        "Avoid abstract reasoning or multi-step inference."
    ),
    2: (
        "Form 2 (Secondary 2, ~age 13). Slightly more complex than F1. "
        "Questions can require basic application and simple analysis. "
        "Still within the Junior Secondary curriculum scope. "
        "Some questions may involve simple data interpretation."
    ),
    3: (
        "Form 3 (Secondary 3, ~age 14). "
        "Questions should bridge junior and senior secondary levels. "
        "Include both recall and application. Some analysis questions are appropriate. "
        "This is the last year before elective streaming."
    ),
    4: (
        "Form 4 (Secondary 4, ~age 15). Senior secondary / HKDSE prep Year 1. "
        "Questions should align with the HKDSE syllabus. "
        "Include application, analysis, and some evaluation. "
        "Follow the style of HKDSE past-paper Section A (easier) questions."
    ),
    5: (
        "Form 5 (Secondary 5, ~age 16). Senior secondary / HKDSE prep Year 2. "
        "Questions should match mid-level HKDSE difficulty. "
        "Mix of Section A and Section B style questions. "
        "Require deeper analysis, multi-step problem solving, and evaluation."
    ),
    6: (
        "Form 6 (Secondary 6, ~age 17). Final HKDSE year. "
        "Questions should closely mirror actual HKDSE exam difficulty. "
        "Include challenging Section B style questions. "
        "Require critical thinking, synthesis, and detailed reasoning."
    ),
}
