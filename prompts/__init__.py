"""Prompts package — central re-export hub.

All prompt data is importable from ``prompts`` directly::

    from prompts import SUBJECT_KNOWLEDGE, CHINESE_WRITING_RUBRIC, ...

Sub-modules:
    prompts.subjects.*           – per-subject knowledge dicts
    prompts.form_difficulty      – FORM_DIFFICULTY_DESCRIPTORS
    prompts.chinese_writing_rubric – CHINESE_WRITING_RUBRIC
    prompts.english_writing_rubric – ENGLISH_WRITING_RUBRIC
"""

from prompts.subjects import SUBJECT_KNOWLEDGE
from prompts.form_difficulty import FORM_DIFFICULTY_DESCRIPTORS
from prompts.chinese_writing_rubric import CHINESE_WRITING_RUBRIC
from prompts.english_writing_rubric import ENGLISH_WRITING_RUBRIC

__all__ = [
    "SUBJECT_KNOWLEDGE",
    "FORM_DIFFICULTY_DESCRIPTORS",
    "CHINESE_WRITING_RUBRIC",
    "ENGLISH_WRITING_RUBRIC",
]
