"""Tavily web search + simple page fetch helpers.

- Kept optional: if tavily-python isn't installed or no API key is set, functions return empty results.
- API key is read from env `TAVILY_API_KEY` or `local_secrets.TAVILY_API_KEY`.

This module is intentionally standalone so routes/AI code can import it without adding more logic to web_app.py.
"""

from __future__ import annotations

import os
import re
import urllib.request
from html.parser import HTMLParser
from typing import Any, Optional

try:
    from tavily import TavilyClient  # type: ignore
except Exception:  # pragma: no cover
    TavilyClient = None

try:
    import local_secrets  # type: ignore
except Exception:  # pragma: no cover
    local_secrets = None


def _get_api_key() -> Optional[str]:
    key = os.environ.get("TAVILY_API_KEY")
    if not key and local_secrets is not None:
        key = getattr(local_secrets, "TAVILY_API_KEY", None)
    key = (key or "").strip()
    return key or None


def get_client() -> Optional[Any]:
    if not TavilyClient:
        return None
    key = _get_api_key()
    if not key:
        return None
    try:
        return TavilyClient(api_key=key)
    except Exception:
        return None


def search(*, query: str, search_depth: str = "advanced", max_results: int = 5) -> dict[str, Any]:
    """Run a Tavily search. Returns dict with at least: {results: [...]}."""
    client = get_client()
    if not client:
        return {"results": []}

    q = (query or "").strip()
    if not q:
        return {"results": []}

    try:
        # tavily-python supports `search_depth`; many versions also support `max_results`.
        return client.search(query=q, search_depth=search_depth, max_results=max_results)
    except TypeError:
        # Older clients may not accept max_results.
        try:
            return client.search(query=q, search_depth=search_depth)
        except Exception:
            return {"results": []}
    except Exception:
        return {"results": []}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str):
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        txt = (data or "").strip()
        if txt:
            self._chunks.append(txt)

    def text(self) -> str:
        return "\n".join(self._chunks)


def fetch_page_text(url: str, *, max_chars: int = 6000, timeout_s: int = 12) -> str:
    """Fetch a web page and extract rough visible text.

    Note: this is a lightweight fallback. Tavily results often already include useful snippets.
    """
    u = (url or "").strip()
    if not u:
        return ""

    # Basic URL sanity check
    if not re.match(r"^https?://", u, flags=re.IGNORECASE):
        return ""

    try:
        req = urllib.request.Request(
            u,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; BaymaxLiteBot/1.0; +https://localhost)"
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # nosec - user-controlled URL; used for user-requested fetch
            raw = resp.read(800_000)
            html = raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""

    parser = _HTMLTextExtractor()
    try:
        parser.feed(html)
    except Exception:
        return ""

    text = parser.text()
    # collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."
    return text


def build_web_context(
    *,
    user_question: str,
    search_depth: str = "advanced",
    max_results: int = 5,
    fetch_top_n_pages: int = 1,
) -> str:
    """Build a compact web context block for an LLM prompt."""
    result = search(query=user_question, search_depth=search_depth, max_results=max_results)
    results = result.get("results")
    if not isinstance(results, list) or not results:
        return ""

    snippets: list[str] = []
    urls: list[str] = []

    for r in results:
        if not isinstance(r, dict):
            continue
        content = (r.get("content") or r.get("snippet") or "").strip()
        url = (r.get("url") or "").strip()
        title = (r.get("title") or "").strip()
        if content:
            line = content
            if title:
                line = f"{title}: {line}"
            if url:
                line = f"{line}\nSource: {url}"
            snippets.append(line)
        if url:
            urls.append(url)

    page_texts: list[str] = []
    for u in urls[: max(0, int(fetch_top_n_pages))]:
        txt = fetch_page_text(u)
        if txt:
            page_texts.append(f"Full page text from {u}:\n{txt}")

    joined = "\n\n".join((snippets + page_texts)[: max_results + fetch_top_n_pages])
    if not joined.strip():
        return ""

    return (
        "Use the following web info to help answer the question. "
        "If the web info is irrelevant or low quality, ignore it.\n\n"
        f"{joined}".strip()
    )
