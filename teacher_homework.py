"""teacher_homework.py

Teacher webpage to input homework into homework.db and view current entries.

- No external dependencies (standard library only)
- DB access via homework_memory.py (DB-only module)

Run:
  python teacher_homework.py
Open:
  http://127.0.0.1:8001

This is local-only by default (127.0.0.1).
"""

from __future__ import annotations

import html
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import homework_memory


def _page(message: str = "") -> str:
    items = homework_memory.list_homeworks(limit=200)

    rows = ""
    for h in items:
        rows += (
            "<tr>"
            f"<td class='mono'>{h.get('id')}</td>"
            f"<td>{html.escape(str(h.get('target_class') or ''))}</td>"
            f"<td>{html.escape(str(h.get('subject') or ''))}</td>"
            f"<td>{html.escape(str(h.get('description') or ''))}</td>"
            f"<td class='mono'>{html.escape(str(h.get('deadline') or ''))}</td>"
            f"<td class='mono'>{html.escape(str(h.get('created_at') or ''))}</td>"
            f"<td><form method='POST' action='/delete' style='margin:0'>"
            f"<input type='hidden' name='id' value='{h.get('id')}' />"
            f"<button type='submit'>Delete</button>"
            f"</form></td>"
            "</tr>"
        )

    if not rows:
        rows = "<tr><td colspan='7'>(no homework yet)</td></tr>"

    msg_html = f"<div class='msg'>{html.escape(message)}</div>" if message else ""

    return f"""<!doctype html>
<html>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>Teacher • Homework Input</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 16px; }}
    .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 12px; margin-bottom: 12px; }}
    label {{ display: block; margin-top: 8px; }}
    input, textarea {{ width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 8px; }}
    textarea {{ min-height: 80px; }}
    button {{ padding: 8px 12px; border-radius: 8px; border: 1px solid #ddd; background: #fff; cursor: pointer; }}
    button:hover {{ background: #f6f6f6; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
    th {{ text-align: left; background: #f6f6f6; position: sticky; top: 0; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }}
    .msg {{ padding: 10px; border-radius: 8px; background: #f6f6f6; margin-bottom: 12px; }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }}
    @media (max-width: 900px) {{ .row {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <h2>Teacher • Homework Input</h2>
  {msg_html}

  <div class='card'>
    <form method='POST' action='/add'>
      <div class='row'>
        <div>
          <label>Target class (e.g. 5A)</label>
          <input name='target_class' placeholder='5A' required />
        </div>
        <div>
          <label>Subject (e.g. Math)</label>
          <input name='subject' placeholder='Math' required />
        </div>
        <div>
          <label>Deadline (ISO date or datetime)</label>
          <input name='deadline' placeholder='2026-01-10 or 2026-01-10T18:00' required />
        </div>
      </div>

      <label>Homework description</label>
      <textarea name='description' placeholder='e.g. Finish worksheet p.12 Q1-10' required></textarea>

      <div style='margin-top:10px;'>
        <button type='submit'>Add homework</button>
      </div>
    </form>
  </div>

  <div class='card'>
    <div style='margin-bottom:8px;'>Database: <span class='mono'>homework.db</span></div>
    <table>
      <thead>
        <tr>
          <th>id</th>
          <th>target_class</th>
          <th>subject</th>
          <th>description</th>
          <th>deadline</th>
          <th>created_at</th>
          <th>actions</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </div>
</body>
</html>"""


def _clean(s: str) -> str:
    return (s or "").strip()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_page().encode("utf-8"))
            return

        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        data = {k: v[0] for k, v in parse_qs(body).items()}

        if parsed.path == "/add":
            target_class = _clean(data.get("target_class", ""))
            subject = _clean(data.get("subject", ""))
            deadline = _clean(data.get("deadline", ""))
            description = _clean(data.get("description", ""))

            if not (target_class and subject and deadline):
                msg = "All fields are required."
            else:
                try:
                    homework_memory.add_homework(subject, target_class, description, deadline)
                    msg = "Homework added."
                except Exception as e:
                    msg = f"Failed to add homework: {e}"

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_page(msg).encode("utf-8"))
            return

        if parsed.path == "/delete":
            try:
                homework_id = int(_clean(data.get("id", "0")) or "0")
                if homework_id > 0:
                    homework_memory.delete_homework(homework_id)
                    msg = "Homework deleted."
                else:
                    msg = "Invalid id."
            except Exception as e:
                msg = f"Failed to delete: {e}"

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_page(msg).encode("utf-8"))
            return

        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Not found")

    def log_message(self, format, *args):
        return


def main() -> None:
    homework_memory.init_db()
    server = HTTPServer(("127.0.0.1", 8001), Handler)
    print("Teacher homework page running:")
    print("  http://127.0.0.1:8001")
    server.serve_forever()


if __name__ == "__main__":
    main()
