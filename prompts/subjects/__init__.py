"""Collect all per-subject HKDSE knowledge into a single SUBJECT_KNOWLEDGE dict."""

from __future__ import annotations
from typing import Any

from .english import ENGLISH_KNOWLEDGE
from .chinese import CHINESE_KNOWLEDGE
from .math import MATH_KNOWLEDGE
from .physics import PHYSICS_KNOWLEDGE
from .chemistry import CHEMISTRY_KNOWLEDGE
from .biology import BIOLOGY_KNOWLEDGE
from .economics import ECONOMICS_KNOWLEDGE
from .geography import GEOGRAPHY_KNOWLEDGE
from .bafs import BAFS_KNOWLEDGE
from .chinese_history import CHINESE_HISTORY_KNOWLEDGE
from .history import HISTORY_KNOWLEDGE
from .m1_m2 import M1_KNOWLEDGE, M2_KNOWLEDGE

SUBJECT_KNOWLEDGE: dict[str, dict[str, Any]] = {
    "English": ENGLISH_KNOWLEDGE,
    "Chinese": CHINESE_KNOWLEDGE,
    "Math": MATH_KNOWLEDGE,
    "Phy": PHYSICS_KNOWLEDGE,
    "Chem": CHEMISTRY_KNOWLEDGE,
    "Bio": BIOLOGY_KNOWLEDGE,
    "Econ": ECONOMICS_KNOWLEDGE,
    "Geog": GEOGRAPHY_KNOWLEDGE,
    "BAFS": BAFS_KNOWLEDGE,
    "Chinese History": CHINESE_HISTORY_KNOWLEDGE,
    "History": HISTORY_KNOWLEDGE,
    "M1": M1_KNOWLEDGE,
    "M2": M2_KNOWLEDGE,
}
