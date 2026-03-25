"""Web-scraping module for Hong Kong scholarships / subsidies.

Data sources (all official HK Government):
- data.gov.hk CSV datasets (Education Bureau):
  * HKSAR Government Scholarship Fund (GSF)
  * Self-financing Post-secondary Scholarship Scheme (SPSS)
  * Mainland University Study Subsidy Scheme (MUSSS)
- WFSFAA (Working Family and Student Financial Assistance Agency):
  * Menu-driven scheme listing with descriptions scraped from overview pages.

The module caches results in memory for a configurable TTL so repeated page loads
don't hammer government servers.
"""

from __future__ import annotations

import csv
import io
import re
import ssl
import threading
import time
import urllib.request
from html.parser import HTMLParser
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_CACHE_TTL_SECONDS = 3600  # re-scrape at most once per hour

_CSV_SOURCES: list[dict[str, str]] = [
    {
        "id": "gsf",
        "name": "HKSAR Government Scholarship Fund",
        "url": "https://www.edb.gov.hk/attachment/datagovhk/Number_and_Amount_of_GSF_en.csv",
        "source_page": "https://data.gov.hk/en-data/dataset/hk-edb-hegsf-gsf",
        "provider": "Education Bureau",
        "description": (
            "Scholarships/Awards granted under the HKSAR Government Scholarship Fund, "
            "including Scholarship for Outstanding Performance, Talent Development Scholarship, "
            "Reaching Out Award, Endeavour Merit Award, and Targeted Scholarship "
            "(including Belt and Road Scholarship)."
        ),
    },
    {
        "id": "spss",
        "name": "Self-financing Post-secondary Scholarship Scheme",
        "url": "https://www.cspe.edu.hk/resources/psi/Number_and_Amount_of_SPSS_en.csv",
        "source_page": "https://data.gov.hk/en-data/dataset/hk-edb-cspe-awards",
        "provider": "Education Bureau",
        "description": (
            "Scholarships/Awards granted under the Self-financing Post-secondary Scholarship Scheme, "
            "including Outstanding Performance Scholarship, Best Progress Award, Talent Development "
            "Scholarship, Reaching Out Award, and Endeavour Scholarship."
        ),
    },
    {
        "id": "musss",
        "name": "Mainland University Study Subsidy Scheme",
        "url": "https://www.edb.gov.hk/attachment/datagovhk/Scholarships_and_Subsidy_in_MUSSS_en.csv",
        "source_page": "https://data.gov.hk/en-data/dataset/hk-edb-hemusss-musss",
        "provider": "Education Bureau",
        "description": (
            "Subsidy for Hong Kong students pursuing undergraduate studies at "
            "mainland higher education institutions. Provides means-tested and "
            "non-means-tested financial assistance."
        ),
    },
]

# WFSFAA scheme definitions — extracted from the official menu at
# https://www.wfsfaa.gov.hk/js/data/en_top_menu.js
# Each tuple: (scheme_name, relative_path, category, short_description)
_WFSFAA_BASE = "https://www.wfsfaa.gov.hk/en/"
_WFSFAA_SCHEMES: list[dict[str, str]] = [
    # Pre-primary
    {
        "id": "kcfrs",
        "name": "Kindergarten & Child Care Centre Fee Remission Scheme (KCFRS)",
        "category": "Pre-primary Level",
        "path": "sfo/preprimary/kcfr/overview.php",
        "provider": "WFSFAA",
    },
    # Primary & Secondary
    {
        "id": "tt",
        "name": "Financial Assistance Schemes for Primary & Secondary Students",
        "category": "Primary & Secondary Level",
        "path": "sfo/primarysecondary/tt/overview.php",
        "provider": "WFSFAA",
    },
    {
        "id": "faeaec",
        "name": "Financial Assistance Scheme for Designated Evening Adult Education Courses (FAEAEC)",
        "category": "Primary & Secondary Level",
        "path": "sfo/primarysecondary/faeaec/overview.php",
        "provider": "WFSFAA",
    },
    {
        "id": "yjd",
        "name": "Diploma of Applied Education (DAE) / Diploma Yi Jin (DYJ) Tuition Fee Reimbursement",
        "category": "Primary & Secondary Level",
        "path": "sfo/primarysecondary/yjd/overview.php",
        "provider": "WFSFAA",
    },
    # Post-secondary & Tertiary
    {
        "id": "tsfs",
        "name": "Tertiary Student Finance Scheme – Publicly-funded Programmes (TSFS)",
        "category": "Post-secondary & Tertiary Level",
        "path": "sfo/postsecondary/tsfs/overview.php",
        "provider": "WFSFAA",
    },
    {
        "id": "nlsft",
        "name": "Non-means-tested Loan Scheme for Full-time Tertiary Students (NLSFT)",
        "category": "Post-secondary & Tertiary Level",
        "path": "sfo/postsecondary/nlsft/overview.php",
        "provider": "WFSFAA",
    },
    {
        "id": "fasp",
        "name": "Financial Assistance Scheme for Post-secondary Students (FASP)",
        "category": "Post-secondary & Tertiary Level",
        "path": "sfo/postsecondary/fasp/overview.php",
        "provider": "WFSFAA",
    },
    {
        "id": "nlsps",
        "name": "Non-means-tested Loan Scheme for Post-secondary Students (NLSPS)",
        "category": "Post-secondary & Tertiary Level",
        "path": "sfo/postsecondary/nlsps/overview.php",
        "provider": "WFSFAA",
    },
    {
        "id": "sts",
        "name": "Student Travel Subsidy (STS) for Tertiary or Post-secondary Students",
        "category": "Post-secondary & Tertiary Level",
        "path": "sfo/postsecondary/sts/overview.php",
        "provider": "WFSFAA",
    },
    {
        "id": "enls",
        "name": "Extended Non-means-tested Loan Scheme (ENLS)",
        "category": "Post-secondary & Tertiary Level / Continuing Education",
        "path": "sfo/postsecondary/enls/overview.php",
        "provider": "WFSFAA",
    },
    # Continuing Education
    {
        "id": "cef",
        "name": "Continuing Education Fund (CEF)",
        "category": "Continuing Education",
        "path": "ce/cef/overview.php",
        "provider": "WFSFAA",
    },
    # Scholarships & Grants via WFSFAA
    {
        "id": "seymf",
        "name": "Sir Edward Youde Memorial Fund",
        "category": "Scholarships & Grants",
        "path": "sfo/seymf/en/index.htm",
        "provider": "WFSFAA",
    },
    {
        "id": "spet",
        "name": "Scholarship for Prospective English Teachers",
        "category": "Scholarships & Grants",
        "path": "other/scholarships/english/9.1.8.htm",
        "provider": "WFSFAA",
    },
    {
        "id": "hkses",
        "name": "Hong Kong Scholarship for Excellence Scheme",
        "category": "Scholarships & Grants",
        "path": "other/scholarships/excellence/9.1.9.htm",
        "provider": "WFSFAA",
    },
    {
        "id": "esf",
        "name": "Education Scholarships Fund",
        "category": "Scholarships & Grants",
        "path": "other/scholarships/education/9.1.7.htm",
        "provider": "WFSFAA",
    },
    {
        "id": "srbtf",
        "name": "Sir Robert Black Trust Fund Postgraduate Scholarships",
        "category": "Scholarships & Grants",
        "path": "other/scholarships/robert/9.1.5.htm",
        "provider": "WFSFAA",
    },
    {
        "id": "agri_tert",
        "name": "Agricultural Products Scholarship Fund – Tertiary Education Awards",
        "category": "Scholarships & Grants",
        "path": "other/scholarships/agricultural/tertiary/9.1.1.2.htm",
        "provider": "WFSFAA",
    },
    {
        "id": "agri_sec",
        "name": "Agricultural Products Scholarship Fund – Senior Secondary Education Awards",
        "category": "Scholarships & Grants",
        "path": "other/scholarships/agricultural/senior/9.1.1.1.htm",
        "provider": "WFSFAA",
    },
    {
        "id": "musss_wfsfaa",
        "name": "Mainland University Study Subsidy Scheme (WFSFAA)",
        "category": "Scholarships & Grants",
        "path": "other/grantsloans/mainland/9.1.13.htm",
        "provider": "WFSFAA",
    },
    {
        "id": "rotary",
        "name": "Hong Kong Rotary Club Students' Loan Fund",
        "category": "Scholarships & Grants",
        "path": "other/grantsloans/rotary/9.1.11.htm",
        "provider": "WFSFAA",
    },
    {
        "id": "singtao",
        "name": "Sing Tao Charitable Foundation Students' Loan Fund",
        "category": "Scholarships & Grants",
        "path": "other/grantsloans/singtao/9.1.12.htm",
        "provider": "WFSFAA",
    },
    {
        "id": "grantham",
        "name": "Grantham Scholarships Fund – Grantham Maintenance Grants",
        "category": "Scholarships & Grants",
        "path": "other/grantsloans/grantham/9.1.10.htm",
        "provider": "WFSFAA",
    },
]


# ---------------------------------------------------------------------------
# Simple HTML text extraction
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data: str) -> None:
        if self._skip == 0:
            t = data.strip()
            if t:
                self._chunks.append(t)

    def get_text(self) -> str:
        return " ".join(self._chunks)


def _html_to_text(html: str) -> str:
    ext = _TextExtractor()
    ext.feed(html)
    return ext.get_text()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_SSL_CTX: Optional[ssl.SSLContext] = None


def _ssl_context() -> ssl.SSLContext:
    global _SSL_CTX
    if _SSL_CTX is None:
        _SSL_CTX = ssl.create_default_context()
    return _SSL_CTX


def _fetch(url: str, timeout: int = 15) -> str:
    """Fetch a URL and return decoded text. Returns empty string on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (BaymaxLite student-aid)"})
        resp = urllib.request.urlopen(req, context=_ssl_context(), timeout=timeout)
        raw = resp.read()
        # Detect UTF-16 BOM (LE: ff fe, BE: fe ff)
        if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
            return raw.decode("utf-16", errors="replace")
        # Try BOM-marked UTF-8 first, then plain UTF-8
        return raw.decode("utf-8-sig", errors="replace")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# CSV scraping  (data.gov.hk)
# ---------------------------------------------------------------------------

def _parse_csv_dataset(source: dict[str, str]) -> dict[str, Any]:
    """Fetch CSV from source URL and return structured data."""
    text = _fetch(source["url"])
    if not text.strip():
        return {**source, "rows": [], "error": "Could not fetch CSV data."}

    # Clean up: strip BOM, normalize line endings
    cleaned = text.replace('\ufeff', '').replace('\r\n', '\n').replace('\r', '\n')
    lines = cleaned.strip().split('\n')

    # Some CSVs (e.g. MUSSS) wrap each entire row in double-quotes,
    # which makes the commas invisible to csv.DictReader. Strip outer quotes.
    cleaned_lines: list[str] = []
    for line in lines:
        line = line.strip()
        if line.startswith('"') and line.endswith('"'):
            inner = line[1:-1]
            # Only unwrap if inner content doesn't contain unescaped quotes
            if '"' not in inner:
                line = inner
        cleaned_lines.append(line)

    reader = csv.DictReader(io.StringIO('\n'.join(cleaned_lines)))
    rows: list[dict[str, str]] = []
    for row in reader:
        rows.append(dict(row))

    return {**source, "rows": rows}


# ---------------------------------------------------------------------------
# WFSFAA scheme scraping
# ---------------------------------------------------------------------------

def _scrape_scheme_overview(scheme: dict[str, str]) -> dict[str, Any]:
    """Fetch a WFSFAA scheme overview page and extract key text."""
    url = _WFSFAA_BASE + scheme["path"]
    html = _fetch(url)
    description = ""
    if html:
        text = _html_to_text(html)
        # Try to extract meaningful content — look for text after the scheme name
        name_lower = scheme["name"].lower()
        idx = text.lower().find("overview")
        if idx >= 0:
            after = text[idx + len("overview"):].strip()
            # Take first ~500 chars of meaningful content
            description = after[:500].strip()
        if not description:
            description = text[:500].strip()

        # Clean up JS artifacts
        description = re.sub(r'\$\(function.*?\}\);?', '', description, flags=re.DOTALL)
        description = re.sub(r'var\s+\w+\s*=.*?;', '', description)
        description = re.sub(r'\s+', ' ', description).strip()

    return {
        **scheme,
        "url": url,
        "description": description or f"Details available at {url}",
    }


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {}
_cache_ts: float = 0.0


def _is_cache_valid() -> bool:
    return bool(_cache) and (time.time() - _cache_ts) < _CACHE_TTL_SECONDS


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_all_scholarships(force_refresh: bool = False) -> dict[str, Any]:
    """Return combined scholarship / subsidy data.

    Returns dict:
      {
        "csv_datasets": [ ... ],     # parsed CSV data from data.gov.hk
        "schemes": [ ... ],          # WFSFAA scheme info with descriptions
        "last_updated": float,       # epoch timestamp
      }
    """
    global _cache, _cache_ts

    if not force_refresh and _is_cache_valid():
        return _cache

    with _cache_lock:
        # Double-check after acquiring lock
        if not force_refresh and _is_cache_valid():
            return _cache

        csv_datasets: list[dict[str, Any]] = []
        for src in _CSV_SOURCES:
            try:
                csv_datasets.append(_parse_csv_dataset(src))
            except Exception:
                csv_datasets.append({**src, "rows": [], "error": "Parse error"})

        schemes: list[dict[str, Any]] = []
        for sch in _WFSFAA_SCHEMES:
            try:
                schemes.append(_scrape_scheme_overview(sch))
            except Exception:
                schemes.append({**sch, "url": _WFSFAA_BASE + sch["path"], "description": ""})

        _cache = {
            "csv_datasets": csv_datasets,
            "schemes": schemes,
            "last_updated": time.time(),
        }
        _cache_ts = time.time()
        return _cache


def build_scholarship_context() -> str:
    """Build a text summary of all scholarships for use as AI context."""
    data = get_all_scholarships()
    parts: list[str] = []

    parts.append("=== Hong Kong Scholarships / Subsidies Database (Live from data.gov.hk & WFSFAA) ===\n")

    for ds in data.get("csv_datasets", []):
        parts.append(f"\n--- {ds['name']} ---")
        parts.append(f"Provider: {ds.get('provider', 'N/A')}")
        parts.append(f"Source: {ds.get('source_page', ds.get('url', ''))}")
        parts.append(f"Description: {ds.get('description', '')}")
        rows = ds.get("rows", [])
        if rows:
            parts.append("Historical data (most recent years):")
            for row in rows[-5:]:
                parts.append(f"  {row}")
        parts.append("")

    parts.append("\n--- WFSFAA Financial Assistance Schemes ---")
    for sch in data.get("schemes", []):
        parts.append(f"\nScheme: {sch['name']}")
        parts.append(f"Category: {sch.get('category', 'N/A')}")
        parts.append(f"Provider: {sch.get('provider', 'N/A')}")
        parts.append(f"URL: {sch.get('url', '')}")
        desc = sch.get("description", "")
        if desc:
            parts.append(f"Overview: {desc[:300]}")

    return "\n".join(parts)
