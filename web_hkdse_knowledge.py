"""HKDSE & HK secondary school question knowledge base.

Thin wrapper that re-exports everything from the ``prompts`` package so
existing imports (``import web_hkdse_knowledge as hkdse``) keep working.
"""

from __future__ import annotations

from typing import Any

from prompts import (
    SUBJECT_KNOWLEDGE,
    FORM_DIFFICULTY_DESCRIPTORS,
    CHINESE_WRITING_RUBRIC,
    ENGLISH_WRITING_RUBRIC,
)


# ─── Helper: get knowledge for a subject ─────────────────────────────────

def get_subject_knowledge(subject: str) -> dict[str, Any]:
    """Return the knowledge dict for a subject, or empty dict."""
    return SUBJECT_KNOWLEDGE.get(subject, {})


def get_form_descriptor(form_number: int) -> str:
    """Return the form-level difficulty descriptor."""
    return FORM_DIFFICULTY_DESCRIPTORS.get(form_number, FORM_DIFFICULTY_DESCRIPTORS.get(4, ""))


def get_test_modes(subject: str) -> list[str]:
    """Return available test modes for a subject."""
    k = get_subject_knowledge(subject)
    return k.get("test_modes", ["standard"])


def get_writing_prompt(subject: str, form_number: int) -> str:
    """Return a random writing prompt for the given subject and form level."""
    import random
    k = get_subject_knowledge(subject)
    prompts = k.get("writing_prompts_by_form", {})
    bucket = "senior" if form_number >= 4 else "junior"
    choices = prompts.get(bucket, prompts.get("senior", []))
    if choices:
        return random.choice(choices)
    return ""


def get_set_texts_list() -> list[str]:
    """Return the 12 HKDSE set texts for Chinese."""
    return SUBJECT_KNOWLEDGE.get("Chinese", {}).get("set_texts_list", [])


def get_writing_rubric(subject: str) -> str:
    """Return the writing rubric for a subject."""
    if subject == "Chinese":
        return CHINESE_WRITING_RUBRIC
    elif subject == "English":
        return ENGLISH_WRITING_RUBRIC
    return ""
