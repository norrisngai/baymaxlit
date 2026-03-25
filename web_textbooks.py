"""Hong Kong secondary school textbook data and content fetching.

Approach (similar to web_scholarships.py):
- Curated list of commonly used HK DSE textbooks by subject.
- Uses EDB Recommended Textbook List as reference.
- For actual content, uses Tavily web search to find relevant study materials
  when a student selects a textbook + chapter + topic.

Data source: https://www.edb.gov.hk/en/curriculum-development/resource-support/textbook-info/index.html
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Optional

try:
    import web_tavily
except Exception:
    web_tavily = None

# ---------------------------------------------------------------------------
# Curated HK DSE Textbook Catalogue
# ---------------------------------------------------------------------------
# Organised by subject.  Each entry has:
#   publisher, series, form_levels (list of ints), chapters (list of dicts)
#
# Chapter lists are representative – students can also type custom chapter names.

HK_TEXTBOOKS: dict[str, list[dict[str, Any]]] = {
    "English": [
        {
            "id": "eng_lae",
            "publisher": "Longman / Pearson",
            "series": "Longman Activate English",
            "form_levels": [1, 2, 3, 4, 5, 6],
            "chapters": [],
        },
        {
            "id": "eng_oup",
            "publisher": "Oxford University Press",
            "series": "Oxford English",
            "form_levels": [1, 2, 3, 4, 5, 6],
            "chapters": [],
        },
    ],
    "Chinese": [
        {
            "id": "chi_qj",
            "publisher": "啟思出版社 / Keys Press",
            "series": "啟思中國語文",
            "form_levels": [1, 2, 3, 4, 5, 6],
            "chapters": [],
        },
        {
            "id": "chi_yl",
            "publisher": "雅集出版社 / Aristo",
            "series": "雅集中國語文",
            "form_levels": [1, 2, 3, 4, 5, 6],
            "chapters": [],
        },
    ],
    "Math": [
        {
            "id": "math_nss",
            "publisher": "Oxford University Press",
            "series": "New Century Mathematics (2nd Ed)",
            "form_levels": [1, 2, 3, 4, 5, 6],
            "chapters": [
                {"num": 1, "title": "Directed Numbers and the Number Line"},
                {"num": 2, "title": "Introduction to Algebra"},
                {"num": 3, "title": "Algebraic Equations in One Unknown"},
                {"num": 4, "title": "Percentages"},
                {"num": 5, "title": "Introduction to Geometry"},
                {"num": 6, "title": "Areas and Volumes"},
                {"num": 7, "title": "Introduction to Statistics"},
                {"num": 8, "title": "Coordinates Geometry"},
                {"num": 9, "title": "Linear Equations"},
                {"num": 10, "title": "Trigonometry"},
                {"num": 11, "title": "Exponential and Logarithmic Functions"},
                {"num": 12, "title": "sequences and Series"},
                {"num": 13, "title": "Probability"},
                {"num": 14, "title": "Differentiation"},
            ],
        },
        {
            "id": "math_lnf",
            "publisher": "Longman / Pearson",
            "series": "Longman New Senior Secondary Mathematics",
            "form_levels": [4, 5, 6],
            "chapters": [],
        },
        {
            "id": "math_aristo",
            "publisher": "Aristo",
            "series": "HKDSE Mathematics in Action",
            "form_levels": [1, 2, 3, 4, 5, 6],
            "chapters": [],
        },
    ],
    "Phy": [
        {
            "id": "phy_aristo",
            "publisher": "Aristo",
            "series": "HKDSE Physics in Life",
            "form_levels": [4, 5, 6],
            "chapters": [
                {"num": 1, "title": "Position and Movement"},
                {"num": 2, "title": "Force and Motion"},
                {"num": 3, "title": "Force and Pressure"},
                {"num": 4, "title": "Energy and Power"},
                {"num": 5, "title": "Momentum"},
                {"num": 6, "title": "Projectile Motion"},
                {"num": 7, "title": "Circular Motion"},
                {"num": 8, "title": "Gravitation"},
                {"num": 9, "title": "Heat and Internal Energy"},
                {"num": 10, "title": "Transfer Processes"},
                {"num": 11, "title": "Change of State"},
                {"num": 12, "title": "Gases"},
                {"num": 13, "title": "Waves"},
                {"num": 14, "title": "Light"},
                {"num": 15, "title": "Sound"},
                {"num": 16, "title": "Electrostatics"},
                {"num": 17, "title": "Electric Circuits"},
                {"num": 18, "title": "Domestic Electricity"},
                {"num": 19, "title": "Electromagnetism"},
                {"num": 20, "title": "Electromagnetic Induction"},
                {"num": 21, "title": "Radioactivity and Nuclear Energy"},
            ],
        },
        {
            "id": "phy_oup",
            "publisher": "Oxford University Press",
            "series": "New Senior Secondary Physics at Work",
            "form_levels": [4, 5, 6],
            "chapters": [],
        },
    ],
    "Chem": [
        {
            "id": "chem_aristo",
            "publisher": "Aristo",
            "series": "HKDSE Chemistry in Life",
            "form_levels": [4, 5, 6],
            "chapters": [
                {"num": 1, "title": "Planet Earth"},
                {"num": 2, "title": "Microscopic World I"},
                {"num": 3, "title": "Metals"},
                {"num": 4, "title": "Acids and Bases"},
                {"num": 5, "title": "Fossil Fuels and Carbon Compounds"},
                {"num": 6, "title": "Microscopic World II"},
                {"num": 7, "title": "Redox Reactions, Chemical Cells and Electrolysis"},
                {"num": 8, "title": "Chemical Reactions and Energy"},
                {"num": 9, "title": "Rate of Reaction"},
                {"num": 10, "title": "Chemical Equilibrium"},
                {"num": 11, "title": "Chemistry of Carbon Compounds"},
                {"num": 12, "title": "Analytical Chemistry"},
                {"num": 13, "title": "Patterns in the Chemical World"},
                {"num": 14, "title": "Industrial Chemistry"},
            ],
        },
        {
            "id": "chem_oup",
            "publisher": "Oxford University Press",
            "series": "New 21st Century Chemistry",
            "form_levels": [4, 5, 6],
            "chapters": [],
        },
    ],
    "Bio": [
        {
            "id": "bio_aristo",
            "publisher": "Aristo",
            "series": "HKDSE Biology in Life",
            "form_levels": [4, 5, 6],
            "chapters": [
                {"num": 1, "title": "Introducing Biology"},
                {"num": 2, "title": "Cells and Molecules of Life"},
                {"num": 3, "title": "Enzymes"},
                {"num": 4, "title": "Nutrition in Humans"},
                {"num": 5, "title": "Gaseous Exchange in Humans"},
                {"num": 6, "title": "Transport in Humans"},
                {"num": 7, "title": "Movement and Support in Humans"},
                {"num": 8, "title": "Coordination and Response in Humans"},
                {"num": 9, "title": "Reproduction, Growth and Development"},
                {"num": 10, "title": "Molecular Genetics"},
                {"num": 11, "title": "Genetic Diseases and Genetic Engineering"},
                {"num": 12, "title": "Biodiversity and Evolution"},
                {"num": 13, "title": "Ecosystems"},
                {"num": 14, "title": "Photosynthesis"},
                {"num": 15, "title": "Cellular Respiration"},
            ],
        },
        {
            "id": "bio_oup",
            "publisher": "Oxford University Press",
            "series": "New Senior Secondary Mastering Biology",
            "form_levels": [4, 5, 6],
            "chapters": [],
        },
    ],
    "Econ": [
        {
            "id": "econ_aristo",
            "publisher": "Aristo",
            "series": "HKDSE Economics in Life",
            "form_levels": [4, 5, 6],
            "chapters": [
                {"num": 1, "title": "Scarcity, Choice and Cost"},
                {"num": 2, "title": "Demand, Supply and Market Equilibrium"},
                {"num": 3, "title": "Elasticity"},
                {"num": 4, "title": "Government Intervention"},
                {"num": 5, "title": "Efficiency, Equity and the Role of Government"},
                {"num": 6, "title": "Measurement of Economic Performance"},
                {"num": 7, "title": "National Income Determination"},
                {"num": 8, "title": "Money and Banking"},
                {"num": 9, "title": "Fiscal and Monetary Policy"},
                {"num": 10, "title": "International Trade"},
            ],
        },
    ],
    "BAFS": [
        {
            "id": "bafs_aristo",
            "publisher": "Aristo",
            "series": "HKDSE BAFS in Life",
            "form_levels": [4, 5, 6],
            "chapters": [
                {"num": 1, "title": "Introduction to Business Environment"},
                {"num": 2, "title": "Forms of Business Organisations"},
                {"num": 3, "title": "Management Functions"},
                {"num": 4, "title": "Financial Accounting"},
                {"num": 5, "title": "Cost Accounting"},
                {"num": 6, "title": "Personal Finance"},
            ],
        },
    ],
    "Geog": [
        {
            "id": "geog_aristo",
            "publisher": "Aristo",
            "series": "HKDSE Geography in Life",
            "form_levels": [4, 5, 6],
            "chapters": [
                {"num": 1, "title": "Opportunities and Risks — Is It Worth Living in a Tectonically Active Area?"},
                {"num": 2, "title": "Managing Rivers and Coastal Environments"},
                {"num": 3, "title": "Changing Climate and Rising Sea Level"},
                {"num": 4, "title": "Building a Sustainable City — Are Environmental and Economic Sustainability Possible?"},
                {"num": 5, "title": "Combating Famine — Is Growing More Food the Answer?"},
                {"num": 6, "title": "Disappearing Green Canopy — Deforestation"},
                {"num": 7, "title": "Global Shift of Manufacturing Industry"},
            ],
        },
    ],
    "Chinese History": [
        {
            "id": "chist_modern",
            "publisher": "現代教育 / Modern Educational Research Society",
            "series": "新探索中國史",
            "form_levels": [4, 5, 6],
            "chapters": [],
        },
    ],
    "History": [
        {
            "id": "hist_oup",
            "publisher": "Oxford University Press",
            "series": "Exploring History",
            "form_levels": [4, 5, 6],
            "chapters": [
                {"num": 1, "title": "Modernisation and Transformation in 20th Century Asia"},
                {"num": 2, "title": "Conflicts and Cooperation in the 20th Century"},
                {"num": 3, "title": "Hong Kong: Growth and Transformation"},
            ],
        },
    ],
    "M1": [
        {
            "id": "m1_aristo",
            "publisher": "Aristo",
            "series": "HKDSE Mathematics M1",
            "form_levels": [4, 5, 6],
            "chapters": [
                {"num": 1, "title": "Binomial Expansion"},
                {"num": 2, "title": "Exponential and Logarithmic Functions"},
                {"num": 3, "title": "Differentiation"},
                {"num": 4, "title": "Applications of Differentiation"},
                {"num": 5, "title": "Integration"},
                {"num": 6, "title": "Applications of Integration"},
                {"num": 7, "title": "Probability"},
                {"num": 8, "title": "Probability Distributions, Expectation and Variance"},
                {"num": 9, "title": "The Normal Distribution"},
                {"num": 10, "title": "Sampling Distribution and Statistical Inference"},
            ],
        },
    ],
    "M2": [
        {
            "id": "m2_aristo",
            "publisher": "Aristo",
            "series": "HKDSE Mathematics M2",
            "form_levels": [4, 5, 6],
            "chapters": [
                {"num": 1, "title": "Mathematical Induction"},
                {"num": 2, "title": "Binomial Theorem"},
                {"num": 3, "title": "Trigonometry"},
                {"num": 4, "title": "Limits and Differentiation"},
                {"num": 5, "title": "Applications of Differentiation"},
                {"num": 6, "title": "Integration"},
                {"num": 7, "title": "Applications of Definite Integration"},
                {"num": 8, "title": "Matrices and Systems of Linear Equations"},
                {"num": 9, "title": "Vectors"},
            ],
        },
    ],
}

# EDB Textbook Information webpage — for reference / future scraping
EDB_TEXTBOOK_LIST_URL = "https://www.edb.gov.hk/en/curriculum-development/resource-support/textbook-info/index.html"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_subjects() -> list[str]:
    """Return all subjects that have textbook entries."""
    return list(HK_TEXTBOOKS.keys())


def get_textbooks_for_subject(subject: str) -> list[dict[str, Any]]:
    """Return textbook list for a given subject."""
    return HK_TEXTBOOKS.get(subject, [])


def get_textbook_by_id(textbook_id: str) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Lookup a textbook by its unique id. Returns (subject, textbook_dict) or (None, None)."""
    for subject, books in HK_TEXTBOOKS.items():
        for book in books:
            if book["id"] == textbook_id:
                return subject, book
    return None, None


def fetch_textbook_content(
    *,
    subject: str,
    textbook_series: str,
    chapter_title: str,
    page_range: str = "",
) -> str:
    """Use Tavily web search to find relevant study content for a textbook chapter.

    This is the key approach: rather than hosting copyrighted textbook PDFs, we
    search the web for publicly available study materials, notes, and summaries
    related to the HK DSE syllabus topic.
    """
    if web_tavily is None:
        return ""

    # Build a targeted search query
    query_parts = [
        f"Hong Kong DSE {subject}",
        f'"{chapter_title}"',
    ]
    if page_range:
        query_parts.append(f"pages {page_range}")
    query_parts.append("study notes summary")

    query = " ".join(query_parts)

    try:
        ctx = web_tavily.build_web_context(
            user_question=query,
            search_depth="advanced",
            max_results=5,
            fetch_top_n_pages=2,
        )
        return ctx or ""
    except Exception:
        return ""


def build_textbook_source_content(
    *,
    subject: str,
    textbook_id: str,
    chapter: str,
    page_range: str = "",
) -> tuple[str, str]:
    """Build source content for a textbook selection.

    Returns (title, content) tuple.
    """
    _subj, book = get_textbook_by_id(textbook_id)
    if not book:
        return ("Unknown textbook", "")

    title = f"{book['series']} — {chapter}"
    if page_range:
        title += f" (pp. {page_range})"

    # Fetch web content for this topic
    web_content = fetch_textbook_content(
        subject=subject,
        textbook_series=book["series"],
        chapter_title=chapter,
        page_range=page_range,
    )

    content_parts = [
        f"Subject: {subject}",
        f"Textbook: {book['series']} ({book['publisher']})",
        f"Chapter/Topic: {chapter}",
    ]
    if page_range:
        content_parts.append(f"Page range: {page_range}")

    if web_content:
        content_parts.append(f"\n--- Web reference materials ---\n{web_content}")
    else:
        content_parts.append(
            "\n(No web content could be fetched. The AI will use its general knowledge of the HK DSE syllabus for this topic.)"
        )

    return title, "\n".join(content_parts)
