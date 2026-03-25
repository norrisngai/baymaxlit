"""Upload helpers for chat attachments.

Purpose: allow students to attach a document or image to a message.
- Documents: extract text (PDF/DOCX/TXT/MD/CSV) and pass to the model.
- Images: pass raw bytes + mime type to the model (if model supports vision).

Binary files are not persisted; only extracted text and the user's message are stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class UploadResult:
    filename: str
    mime_type: str
    kind: str  # 'image' | 'document' | 'text'
    extracted_text: str = ""
    image_bytes: bytes = b""


_TEXT_EXTS = {".txt", ".md", ".csv", ".json"}


def _ext_lower(filename: str) -> str:
    name = (filename or "").strip().lower()
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def process_upload(*, filename: str, mime_type: str, raw: bytes) -> UploadResult:
    filename = (filename or "upload").strip() or "upload"
    mime_type = (mime_type or "application/octet-stream").strip().lower()
    ext = _ext_lower(filename)

    if mime_type.startswith("image/"):
        return UploadResult(filename=filename, mime_type=mime_type, kind="image", image_bytes=raw)

    if ext == ".pdf" or mime_type == "application/pdf":
        try:
            from pypdf import PdfReader
        except Exception as e:  # pragma: no cover
            raise RuntimeError("PDF upload requires 'pypdf' installed") from e

        try:
            import io

            reader = PdfReader(io.BytesIO(raw))
            parts: list[str] = []
            for page in reader.pages:
                txt = (page.extract_text() or "").strip()
                if txt:
                    parts.append(txt)
            text = "\n\n".join(parts).strip()
        except Exception as e:
            raise RuntimeError(f"Failed to read PDF: {e}") from e

        header = f"[Uploaded PDF: {filename} | extracted_at={_now_iso()}]\n"
        return UploadResult(filename=filename, mime_type=mime_type, kind="document", extracted_text=header + (text or "(No text found in PDF.)"))

    if ext == ".docx" or mime_type in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }:
        try:
            import io

            from docx import Document
        except Exception as e:  # pragma: no cover
            raise RuntimeError("DOCX upload requires 'python-docx' installed") from e

        try:
            doc = Document(io.BytesIO(raw))
            text = "\n".join((p.text or "").rstrip() for p in doc.paragraphs if (p.text or "").strip()).strip()
        except Exception as e:
            raise RuntimeError(f"Failed to read DOCX: {e}") from e

        header = f"[Uploaded DOCX: {filename} | extracted_at={_now_iso()}]\n"
        return UploadResult(filename=filename, mime_type=mime_type, kind="document", extracted_text=header + (text or "(No text found in DOCX.)"))

    if ext in _TEXT_EXTS or mime_type.startswith("text/"):
        decoded = ""
        for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                decoded = raw.decode(enc)
                break
            except Exception:
                continue
        decoded = (decoded or "").strip()
        header = f"[Uploaded text file: {filename} | extracted_at={_now_iso()}]\n"
        return UploadResult(filename=filename, mime_type=mime_type, kind="text", extracted_text=header + (decoded or "(Empty file.)"))

    raise RuntimeError("Unsupported file type. Upload an image, PDF, DOCX, or text file.")
