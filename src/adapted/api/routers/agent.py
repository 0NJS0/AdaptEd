from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...logging.logger import get_logger
from ...schemas.api import PipelineResult
from ...tasks.runner import submit_pipeline
from ..deps import AnyUserDep

log = get_logger("adapted.api.agent")
router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRunRequest(BaseModel):
    intent: str
    payload: dict[str, object] = Field(default_factory=dict)
    require_approval: bool = False


@router.post("/run", response_model=PipelineResult)
def run_agent_pipeline(
    body: AgentRunRequest,
    user: AnyUserDep,
) -> PipelineResult:
    """Kick off a supervisor-routed multi-agent workflow in the background.

    Returns immediately with the task id; poll ``GET /agent/tasks/{task_id}``
    for the outcome (status: started -> success | failed). The pipeline runs in
    a worker thread with its own DB session, so the request never blocks on the
    LLM (which is bounded by the provider timeout, see llm_timeout_seconds).
    """
    from ...agents.supervisor import WORKFLOWS

    if body.intent not in WORKFLOWS:
        raise HTTPException(400, f"Unknown intent '{body.intent}'")
    try:
        task_id, correlation_id = submit_pipeline(
            body.intent, body.payload, user.id, require_approval=body.require_approval
        )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        log.error("agent_pipeline_submit_error", intent=body.intent, error=str(exc))
        raise HTTPException(500, f"Pipeline submission failed: {exc}") from exc
    status = "awaiting_approval" if body.require_approval else "started"
    return PipelineResult(task_id=task_id, correlation_id=correlation_id, status=status)
