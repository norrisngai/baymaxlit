"""Minimal, safe Markdown rendering for chat output.

We store messages as plain text, but want the UI to render:
- Headings (#, ##, ###)
- Bold (**text**)
- Italic (*text*)
- Bullet lists (- item, * item)
- Code blocks ``` and inline `code`

Security: escapes all HTML first, then emits a small set of tags.
"""

from __future__ import annotations

import html
import re


_CODEBLOCK_RE = re.compile(r"```(.*?)```", flags=re.DOTALL)
_FULL_FENCE_RE = re.compile(r"^```(?P<lang>[a-zA-Z0-9_-]+)?\s*\n(?P<body>[\s\S]*?)\n```\s*$")


def _render_inline(text: str) -> str:
    # Inline code first (no further formatting inside).
    text = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", text)

    # Markdown links: [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\((\s*https?://[^\s)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        text,
    )

    # Bare URLs that aren't already inside an href
    text = re.sub(
        r'(?<!href=")(?<!">)(https?://[^\s<)]+)',
        r'<a href="\1" target="_blank" rel="noopener">\1</a>',
        text,
    )

    # Bold then italic.
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)

    # Italic: single asterisks around non-space content.
    # Keep it conservative to avoid eating bullet markers.
    text = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", text)
    return text


def render_markdown(text: str) -> str:
    raw = (text or "")
    if not raw.strip():
        return ""

    # If the entire message is wrapped in a single fenced block (common LLM mistake),
    # unwrap it when it's likely markdown so formatting doesn't appear "crazy".
    m_full = _FULL_FENCE_RE.match(raw.strip())
    if m_full:
        lang = (m_full.group("lang") or "").strip().lower()
        body = (m_full.group("body") or "")

        # Sometimes a model does:
        # ```
        # markdown
        # ## Title
        # ...
        # ```
        body_stripped = body.lstrip("\n")
        if body_stripped.lower().startswith("markdown\n"):
            body = body_stripped[len("markdown\n") :]
        elif body_stripped.lower().startswith("md\n"):
            body = body_stripped[len("md\n") :]

        looks_like_markdown = any(
            token in body
            for token in ("# ", "## ", "### ", "\n# ", "\n## ", "\n### ", "\n- ", "\n* ", "**", "---", "\n---")
        )
        if lang in {"", "md", "markdown"} and looks_like_markdown:
            raw = body

    # Escape HTML to avoid XSS.
    escaped = html.escape(raw, quote=False)

    # Extract fenced code blocks, replace with placeholders.
    codeblocks: list[str] = []

    def _codeblock_sub(m: re.Match) -> str:
        inner = m.group(1) or ""
        # Strip a single leading newline if present.
        inner = inner.lstrip("\n")
        codeblocks.append(f"<pre><code>{inner}</code></pre>")
        return f"@@CODEBLOCK_{len(codeblocks) - 1}@@"

    escaped = _CODEBLOCK_RE.sub(_codeblock_sub, escaped)

    lines = escaped.split("\n")
    out: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in lines:
        l = line.rstrip()

        # Headings
        if l.startswith("### "):
            close_list()
            out.append(f"<h3>{_render_inline(l[4:])}</h3>")
            continue
        if l.startswith("## "):
            close_list()
            out.append(f"<h2>{_render_inline(l[3:])}</h2>")
            continue
        if l.startswith("# "):
            close_list()
            out.append(f"<h1>{_render_inline(l[2:])}</h1>")
            continue

        # Bullets
        m = re.match(r"^\s*([\-*])\s+(.*)$", l)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_render_inline(m.group(2))}</li>")
            continue

        # Blank line
        if not l.strip():
            close_list()
            continue

        # Paragraph
        close_list()
        out.append(f"<p>{_render_inline(l)}</p>")

    close_list()

    html_out = "\n".join(out)

    # Restore code blocks (already safe, contains escaped inner).
    for i, block in enumerate(codeblocks):
        html_out = html_out.replace(f"@@CODEBLOCK_{i}@@", block)

    return html_out
