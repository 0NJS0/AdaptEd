"""Table-aware document reader for OBE outlines.

The shared ``rag.parser`` reads DOCX *paragraphs* only, which is right for prose
textbooks but wrong for course outlines — where the CO matrix, PO indicators and
assessment map all live in Word *tables*. This reader flattens PDF text and,
crucially, DOCX paragraphs **and tables in document order**, so the extractor
sees the full outline.
"""

from __future__ import annotations

import io
from pathlib import Path

SUPPORTED_OUTLINE_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")


def read_outline_text(path: Path, filename: str | None = None) -> str:
    """Read a course outline from disk into flat text (tables included)."""
    ext = Path(filename or path).suffix.lower()
    if ext == ".pdf":
        return _read_pdf(str(path))
    if ext == ".docx":
        return _read_docx(str(path))
    if ext in (".txt", ".md"):
        return Path(path).read_text(encoding="utf-8", errors="replace")
    raise ValueError(f"Unsupported outline type '{ext}'. Use .pdf, .docx, .txt or .md.")


def read_outline_bytes(data: bytes, filename: str) -> str:
    """Read a course outline from raw bytes (e.g. an HTTP upload) into flat text.

    Same table-aware handling as :func:`read_outline_text`, but from an in-memory
    stream so callers never have to touch the filesystem.
    """
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return _read_pdf(io.BytesIO(data))
    if ext == ".docx":
        return _read_docx(io.BytesIO(data))
    if ext in (".txt", ".md"):
        return data.decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported outline type '{ext}'. Use .pdf, .docx, .txt or .md.")


def _read_pdf(source) -> str:
    from pypdf import PdfReader

    reader = PdfReader(source)
    out: list[str] = []
    for page in reader.pages:
        try:
            out.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            out.append("")
    return "\n".join(out)


def _read_docx(source) -> str:
    from docx import Document as DocxDocument
    from docx.document import Document as _Doc
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = DocxDocument(source)
    parts: list[str] = []
    parent = doc.element.body
    # iterate paragraphs and tables in the order they appear in the document
    for child in parent.iterchildren():
        if isinstance(child, CT_P):
            para = Paragraph(child, doc)
            if para.text.strip():
                parts.append(para.text)
        elif isinstance(child, CT_Tbl):
            table = Table(child, doc)
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                line = " ".join(c for c in cells if c)
                if line.strip():
                    parts.append(line)
    _ = _Doc  # imported for typing clarity; not otherwise used
    return "\n".join(parts)
