"""Extract a structured OBE outline from raw course-outline text.

Best-effort, regex-based parsing of the AIUB CS course-plan template as it
appears once a PDF/DOCX is flattened to text (merged cells, multi-column runs
and stray whitespace included). The extractor never raises on malformed input —
it returns whatever it could recover so the rules engine can still report gaps.

For callers that already hold structured data (tests, API payloads), build an
``OutlineExtraction`` directly instead of going through here.
"""

from __future__ import annotations

import re

from .schema import (
    KPA,
    AssessmentEntry,
    CourseMeta,
    CourseOutcome,
    OutlineExtraction,
    POIndicator,
)

_PO = r"PO-[a-l]-\d"


def _norm(text: str) -> str:
    # collapse runs of whitespace (including newlines) to single spaces
    return re.sub(r"\s+", " ", text or "").strip()


def _section(text: str, start_markers: list[str], end_markers: list[str]) -> str:
    """Return the slice of ``text`` between the first start marker and the next
    end marker (case-insensitive). Falls back to the whole text if not found."""
    low = text.lower()
    start = 0
    for m in start_markers:
        i = low.find(m.lower())
        if i != -1:
            start = i
            break
    end = len(text)
    for m in end_markers:
        j = low.find(m.lower(), start + 1)
        if j != -1:
            end = min(end, j)
    return text[start:end]


def _clean_desc(desc: str) -> str:
    d = _norm(desc)
    d = re.sub(r"^\*+\s*", "", d)  # leading footnote asterisks
    d = re.sub(r"\s*\*+\s*$", "", d)
    return d.strip(" .") + "." if d and not d.endswith(".") else d


def _leading_verb(desc: str) -> str:
    for tok in re.findall(r"[A-Za-z][A-Za-z\-]*", desc):
        if tok.lower() not in {"a", "an", "the", "to", "of"}:
            return tok.lower()
    return ""


def extract_course_meta(text: str) -> CourseMeta:
    meta = CourseMeta()
    m = re.search(r"\b([A-Z]{2,4}\s?\d{3,4})\b\s+([A-Z][A-Za-z0-9 &/\-]{3,60})", text)
    if m:
        meta.code = _norm(m.group(1))
        meta.title = _norm(m.group(2)).title()
    sem = re.search(r"SEMESTER:?\s*([A-Za-z]+,?\s*\d{4}\s*-?\s*\d{2,4})", text, re.I)
    if sem:
        meta.semester = _norm(sem.group(1))
    cr = re.search(r"\b(\d)\s*Credit", text, re.I)
    if cr:
        meta.credit = cr.group(1)
    return meta


def extract_cos(text: str) -> list[CourseOutcome]:
    # Scan the whole document: the CO-matrix rows are uniquely identifiable
    # (a CO id, a description, a single Bloom digit, then a PO indicator) and
    # this survives page breaks that split the matrix across pages. Assessment
    # and weekly rows lack the "<digit> PO-x" shape and are not matched.
    cos: list[CourseOutcome] = []
    seen: set[str] = set()
    # CO<id> <desc> <bloom-level digit> <PO indicator(s)>
    pattern = re.compile(
        rf"CO\s?(\d+)\s*\*{{0,2}}\s*(.{{1,300}}?)\s+([1-6])\s+((?:{_PO}[\s,and]*)+)",
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        cid = f"CO{m.group(1)}"
        if cid in seen:
            continue
        desc = _clean_desc(m.group(2))
        if len(desc) < 5 or len(desc) > 300:  # guard against a runaway match
            continue
        pos = re.findall(_PO, m.group(4))
        cos.append(
            CourseOutcome(
                id=cid,
                description=desc,
                verb=_leading_verb(desc),
                bloom_domain="cognitive",
                bloom_level=int(m.group(3)),
                mapped_pos=[p.upper() for p in pos],
            )
        )
        seen.add(cid)
    return cos


def extract_po_indicators(text: str) -> list[POIndicator]:
    # The PO-indicator row shape ("PO-x-n <def> <Cognitive|Psychomotor|Affective>
    # Level <d>") is specific enough to scan the whole document, which avoids the
    # unreliable section headings (these templates cluster headings, then place
    # the table bodies afterwards, so slicing drops rows).
    inds: list[POIndicator] = []
    seen: set[str] = set()
    pattern = re.compile(
        rf"({_PO})\s+(.{{1,240}}?)\s+(Cognitive|Psychomotor|Affective)\s+Level\s+(\d)",
        re.DOTALL | re.I,
    )
    matches = list(pattern.finditer(text))
    for idx, m in enumerate(matches):
        pid = m.group(1).upper()
        if pid in seen:
            continue
        # window of text after this row up to the next PO row: holds K/P/A codes
        tail_end = matches[idx + 1].start() if idx + 1 < len(matches) else min(
            m.end() + 160, len(text)
        )
        tail = text[m.end() : tail_end]
        kpa = KPA(
            k=[c.upper() for c in re.findall(r"\bK[1-8]\b", tail)],
            p=[c.upper() for c in re.findall(r"\bP[1-7]\b", tail)],
            a=[c.upper() for c in re.findall(r"\bA[1-5]\b", tail)],
        )
        inds.append(
            POIndicator(
                id=pid,
                definition=_clean_desc(m.group(2))[:300],
                bloom_domain=m.group(3).lower(),
                bloom_level=int(m.group(4)),
                kpa=kpa,
            )
        )
        seen.add(pid)
    return inds


def extract_assessment(text: str) -> list[AssessmentEntry]:
    # Assessment rows are uniquely "CO<id> <desc> <PO> <method> Rubric"; only the
    # CO-assessment table has that shape, so a whole-document scan is safe.
    entries: list[AssessmentEntry] = []
    seen: set[str] = set()
    pattern = re.compile(
        rf"CO\s?(\d+)\s*\*{{0,2}}\s*(.{{1,240}}?)\s+((?:{_PO}[\s,and]*)+?)\s+(.{{1,60}}?)\s+Rubric",
        re.DOTALL | re.I,
    )
    for m in pattern.finditer(text):
        cid = f"CO{m.group(1)}"
        if cid in seen:
            continue
        pos = [p.upper() for p in re.findall(_PO, m.group(3))]
        method = _norm(m.group(4))
        method = re.sub(r"^[\s\|]+", "", method)[:60]
        entries.append(AssessmentEntry(co_id=cid, mapped_pos=pos, method=method, rubric="Rubric"))
        seen.add(cid)
    return entries


def extract_weekly_cos(text: str) -> list[str]:
    section = _section(
        text,
        ["Topics to be covered"],
        ["Mapping of PO", "K, P, A", "PO Indicator"],
    )
    ids = {f"CO{n}" for n in re.findall(r"CO\s?(\d+)", section)}
    return sorted(ids, key=lambda s: int(s[2:]))


def extract_weights(text: str) -> dict[str, float]:
    m = re.search(r"Mid\s*(\d{1,3})\s*%\s*\+?\s*Final\s*(\d{1,3})\s*%", text, re.I)
    if m:
        return {"mid": float(m.group(1)), "final": float(m.group(2))}
    return {}


def extract_outline(text: str) -> OutlineExtraction:
    """Parse a full outline's text into a structured ``OutlineExtraction``."""
    return OutlineExtraction(
        course=extract_course_meta(text),
        cos=extract_cos(text),
        po_indicators=extract_po_indicators(text),
        assessment=extract_assessment(text),
        weekly_cos=extract_weekly_cos(text),
        weights=extract_weights(text),
    )
