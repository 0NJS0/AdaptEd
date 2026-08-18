from __future__ import annotations

import re
from dataclasses import dataclass

from .parser import ParsedDocument

HEADING_RE = re.compile(r"^(#{1,4}\s+)?(chapter\s+\d+|[0-9]+(\.[0-9]+)*\s+\S|[A-Z][A-Za-z' ]{3,})$")


@dataclass
class Chunk:
    index: int
    content: str
    page_start: int | None
    page_end: int | None
    heading: str | None


def chunk_document(
    parsed: ParsedDocument, max_chars: int = 1500, overlap: int = 200
) -> list[Chunk]:
    units: list[tuple[str, int | None]] = []
    for page in parsed.pages:
        for line in page.text.split("\n"):
            line = line.strip()
            if not line:
                continue
            units.append((line, page.number))

    chunks: list[Chunk] = []
    current: list[str] = []
    current_len = 0
    current_pages: set[int] = set()
    current_heading: str | None = None
    idx = 0

    def flush() -> None:
        nonlocal current, current_len, current_pages, current_heading, idx
        if not current:
            return
        content = "\n".join(current)
        page_start = min(current_pages) if current_pages else None
        page_end = max(current_pages) if current_pages else None
        chunks.append(Chunk(idx, content, page_start, page_end, current_heading))
        idx += 1
        # keep tail for overlap
        tail = content[-overlap:] if overlap and len(content) > overlap else ""
        current = [tail] if tail else []
        current_len = len(tail)
        current_pages = {page_start} if page_start else set()

    for line, page_no in units:
        if HEADING_RE.match(line) and current and current_len > 400:
            flush()
            current_heading = line
        current.append(line)
        current_len += len(line) + 1
        if page_no is not None:
            current_pages.add(page_no)
        if current_len >= max_chars:
            flush()
            current_heading = None

    flush()
    if not chunks:
        chunks = [Chunk(0, " ".join(u[0] for u in units), None, None, None)]
    return chunks
