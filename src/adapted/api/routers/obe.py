from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ...config import settings
from ...logging.logger import get_logger
from ...obe import runner
from ...obe.document import SUPPORTED_OUTLINE_EXTENSIONS, read_outline_bytes
from ...tasks import runner as task_runner
from ..deps import TeacherDep

log = get_logger("adapted.api.obe")
router = APIRouter(prefix="/obe", tags=["obe"])


class SuggestRequest(BaseModel):
    description: str = Field(..., min_length=3)
    co_id: str | None = None


@router.post("/analyze")
def analyze_outline(
    user: TeacherDep,
    file: Annotated[UploadFile, File(...)],
    polish: Annotated[bool, Form()] = False,
) -> dict:
    """Analyze an uploaded course outline against the AIUB CS OBE Manual.

    File validation runs on the request thread (fast — extension, size,
    text extraction). The actual OBE analysis is submitted to the background
    task pool and runs asynchronously; the endpoint returns a
    ``{task_id, status: "started"}`` response immediately. Poll
    ``GET /agent/tasks/{task_id}`` for the result (shape: ``extraction``,
    ``report``, ``suggestions``, ``summary_markdown``). The source file is
    never stored or modified.
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
    except Exception as exc:
        raise HTTPException(422, f"Could not read the outline: {exc}") from exc
    if not text.strip():
        raise HTTPException(
            422,
            "No extractable text found — the file may be a scanned image "
            "(OCR is not supported).",
        )

    try:
        task_id, correlation_id = task_runner.submit_obe(
            text=text,
            polish=polish,
            filename=file.filename or f"outline{ext}",
            user_id=user.id,
        )
    except Exception as exc:
        log.error("obe_analyze_submit_failed", filename=file.filename, error=str(exc))
        raise HTTPException(502, f"OBE analysis failed: {exc}") from exc

    log.info(
        "obe_analyze_submitted",
        filename=file.filename,
        teacher=user.id,
        task_id=task_id,
        polish=polish,
    )
    return {
        "task_id": task_id,
        "correlation_id": correlation_id,
        "status": "started",
    }


@router.post("/suggest")
def suggest_mapping(user: TeacherDep, body: SuggestRequest) -> dict:
    """Suggest a Bloom level, PO indicator and K-P-A for a single CO description."""
    try:
        return runner.suggest(description=body.description, co_id=body.co_id)
    except Exception as exc:
        raise HTTPException(502, f"Suggestion failed: {exc}") from exc
