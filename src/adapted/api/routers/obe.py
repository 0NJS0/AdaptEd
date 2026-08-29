from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ...config import settings
from ...logging.logger import get_logger
from ...obe import runner
from ...obe.document import SUPPORTED_OUTLINE_EXTENSIONS, read_outline_bytes
from ..deps import TeacherDep

log = get_logger("adapted.api.obe")
router = APIRouter(prefix="/obe", tags=["obe"])


class SuggestRequest(BaseModel):
    description: str = Field(..., min_length=3)
    co_id: str | None = None


class AuthorRequest(BaseModel):
    course_title: str = ""
    subject: str = ""
    topics: list[str] = Field(default_factory=list)
    count: int = Field(4, ge=1, le=12)
    po_hint: str | None = None


class ImproveRequest(BaseModel):
    description: str = Field(..., min_length=3)
    target_level: int | None = Field(None, ge=1, le=6)
    target_po: str | None = None
    co_id: str | None = None


@router.post("/analyze")
def analyze_outline(
    user: TeacherDep,
    file: UploadFile = File(...),
    polish: bool = Form(False),
) -> dict:
    """Analyze an uploaded course outline against the AIUB CS OBE Manual.

    Runs the OBE agent (`obe.summarize`) synchronously — extraction, validation,
    mapping suggestions and the methodology summary — and returns the full
    result. The source file is never stored or modified.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_OUTLINE_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext or '?'}'. Supported: "
            f"{', '.join(SUPPORTED_OUTLINE_EXTENSIONS)}.",
        )
    data = file.file.read()
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "The uploaded file is too large.")

    try:
        text = read_outline_bytes(data, file.filename or f"outline{ext}")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"Could not read the outline: {exc}") from exc
    if not text.strip():
        raise HTTPException(
            422,
            "No extractable text found — the file may be a scanned image "
            "(OCR is not supported).",
        )

    try:
        result = runner.analyze_text(text, polish=polish)
    except Exception as exc:  # noqa: BLE001
        log.error("obe_analyze_failed", filename=file.filename, error=str(exc))
        raise HTTPException(502, f"OBE analysis failed: {exc}") from exc

    log.info(
        "obe_analyze",
        filename=file.filename,
        teacher=user.id,
        errors=result.get("report", {}).get("error_count"),
        warnings=result.get("report", {}).get("warning_count"),
    )
    return result


@router.post("/suggest")
def suggest_mapping(user: TeacherDep, body: SuggestRequest) -> dict:
    """Suggest a Bloom level, PO indicator and K-P-A for a single CO description."""
    try:
        return runner.suggest(description=body.description, co_id=body.co_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Suggestion failed: {exc}") from exc


@router.post("/author")
def author_outcomes(user: TeacherDep, body: AuthorRequest) -> dict:
    """Generate OBE-compliant Course Outcomes for a course/topic set (OBE Authoring agent)."""
    try:
        return runner.author(
            course_title=body.course_title,
            subject=body.subject,
            topics=body.topics,
            count=body.count,
            po_hint=body.po_hint,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Authoring failed: {exc}") from exc


@router.post("/improve")
def improve_outcome(user: TeacherDep, body: ImproveRequest) -> dict:
    """Rewrite a single Course Outcome so its verb, Bloom level and PO/K-P-A align."""
    try:
        return runner.improve(
            description=body.description,
            target_level=body.target_level,
            target_po=body.target_po,
            co_id=body.co_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Improve failed: {exc}") from exc
