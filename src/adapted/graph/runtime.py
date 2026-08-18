from __future__ import annotations

import time
from typing import Any, TypedDict

from langgraph.graph import START, StateGraph

from ..agents.base import AgentResult
from ..agents.message import AgentMessage
from ..agents.supervisor import Supervisor
from ..config import settings
from ..logging.logger import get_logger

log = get_logger("adapted.graph")


class GraphState(TypedDict, total=False):
    task_id: str
    correlation_id: str
    intent: str
    user_id: str | None
    payload: dict[str, Any]
    context: dict[str, Any]
    errors: list[str]
    status: str


class AgentRuntime:
    """Binds DB session/LLM/bus and builds the LangGraph pipeline per run."""

    def __init__(self, db, provider, bus) -> None:
        self.db = db
        self.provider = provider
        self.bus = bus

    def build_agents(self) -> dict[str, Any]:
        from ..agents.curriculum_agent import CurriculumAnalyzerAgent
        from ..agents.grading_agent import GradingAgent
        from ..agents.lesson_agent import LessonAgent
        from ..agents.performance_agent import PerformanceAnalysisAgent
        from ..agents.planner_agent import StudyPlannerAgent
        from ..agents.quiz_agent import QuizAgent
        from ..agents.recommendation_agent import RecommendationAgent

        db, provider, bus = self.db, self.provider, self.bus
        return {
            "curriculum_agent": CurriculumAnalyzerAgent(db, provider, bus),
            "planner_agent": StudyPlannerAgent(db, provider, bus),
            "lesson_agent": LessonAgent(db, provider, bus),
            "quiz_agent": QuizAgent(db, provider, bus),
            "grading_agent": GradingAgent(db, provider, bus),
            "performance_agent": PerformanceAnalysisAgent(db, provider, bus),
            "recommendation_agent": RecommendationAgent(db, provider, bus),
        }

    def _dispatch_node(self, agent_name: str, action: str, receiver_name: str | None = None):
        def _node(state: GraphState) -> dict[str, Any]:
            agent = self.agents[agent_name]
            receiver = receiver_name or agent.name
            merged = self._chain_payload(state, action)
            message = AgentMessage(
                task_id=state["task_id"],
                correlation_id=state["correlation_id"],
                sender="supervisor",
                receiver=receiver,
                action=action,
                payload=merged,
            )
            result = self._run_with_retry(agent, message)
            if result.error:
                return {
                    "errors": [*(state.get("errors") or []), result.error],
                    "status": "failed",
                }
            message.status = "success"
            ctx = {**state["context"]}
            ctx[agent_name] = result.output
            return {"context": ctx, "status": "running"}

        return _node

    def _chain_payload(self, state: GraphState, action: str) -> dict[str, Any]:
        """For the linear adaptive pipeline, later agents consume earlier agents'
        outputs (weak topics, recommendations) as context."""
        payload = {**state["payload"]}
        ctx = state.get("context") or {}
        perf = ctx.get("performance_agent") or {}
        rec = (ctx.get("recommendation_agent") or {}).get("recommendation") or {}

        if action == "recommend.generate":
            payload.update(
                {
                    "weak_topics": perf.get("weak_topics", []),
                    "strong_topics": perf.get("strong_topics", []),
                    "topic_mastery": perf.get("topic_mastery", []),
                    "misconceptions": perf.get("misconceptions", []),
                }
            )
        elif action == "plan.modify":
            payload["mode"] = "modify"
            payload["weak_topic_ids"] = [w["topic_id"] for w in perf.get("weak_topics", [])]
        elif action == "lesson.generate":
            topic_id = rec.get("payload", {}).get("topic_id")
            if topic_id:
                payload["topic_id"] = topic_id
            payload["level"] = payload.get("level") or ("remedial" if rec else "standard")
        elif action == "quiz.generate":
            topic_id = rec.get("payload", {}).get("topic_id")
            if topic_id:
                payload["topic_id"] = topic_id
            payload["quiz_type"] = "reassessment"
            payload["count"] = 5
            payload["variant"] = payload.get("variant", 0) + 1
        return payload

    def _run_with_retry(self, agent: Any, message: AgentMessage) -> Any:
        attempts = 0
        last = None
        while attempts <= settings.agent_max_retries:
            if attempts > 0:
                time.sleep(settings.agent_retry_backoff_seconds * (2**attempts))
                message.status = "retried"
            # savepoint: a failed attempt only rolls back its own writes, never
            # the earlier agents' work (grading, mastery, recommendations, ...)
            savepoint = self.db.begin_nested()
            try:
                result = agent.handle(message)
                if result.error is not None:
                    savepoint.rollback()
                    last = result
                elif agent.output_is_empty(result.output or {}):
                    # schema-valid but vacuum output (free models occasionally
                    # return {"chapters": []}) — roll back and retry rather than
                    # silently "succeed" with empty content
                    savepoint.rollback()
                    last = AgentResult(
                        error=(
                            f"{agent.name} produced empty output on attempt "
                            f"{attempts + 1}; retrying"
                        )
                    )
                else:
                    savepoint.commit()
                    return result
            except Exception as exc:  # noqa: BLE001
                savepoint.rollback()
                last = AgentResult(error=str(exc))
            attempts += 1
        return last

    def compile(self, intent: str):
        self.agents = self.build_agents()
        g = StateGraph(GraphState)
        g.add_node("supervisor", self.supervisor_node)
        g.add_node(
            "curriculum_agent", self._dispatch_node("curriculum_agent", "curriculum.analyze")
        )
        g.add_node("plan_create", self._dispatch_node("planner_agent", "plan.create"))
        g.add_node("plan_modify", self._dispatch_node("planner_agent", "plan.modify"))
        g.add_node("lesson_agent", self._dispatch_node("lesson_agent", "lesson.generate"))
        g.add_node("quiz_agent", self._dispatch_node("quiz_agent", "quiz.generate"))
        g.add_node("grading_agent", self._dispatch_node("grading_agent", "attempt.grade"))
        g.add_node(
            "performance_agent", self._dispatch_node("performance_agent", "performance.analyze")
        )
        g.add_node(
            "recommendation_agent",
            self._dispatch_node("recommendation_agent", "recommend.generate"),
        )
        g.add_node("finalize", self.finalize_node)

        g.add_edge(START, "supervisor")
        g.add_conditional_edges(
            "supervisor",
            self._route,
            {
                "curriculum_agent": "curriculum_agent",
                "plan_create": "plan_create",
                "plan_modify": "plan_modify",
                "lesson_agent": "lesson_agent",
                "quiz_agent": "quiz_agent",
                "grading_agent": "grading_agent",
                "recommendation_agent": "recommendation_agent",
                "finalize": "finalize",
            },
        )
        # linear adaptive pipeline: quiz.submit -> grade -> analyze -> recommend -> adapt -> lesson -> reassess
        g.add_edge("grading_agent", "performance_agent")
        g.add_edge("performance_agent", "recommendation_agent")
        g.add_conditional_edges(
            "recommendation_agent",
            self._is_quiz_submit,
            {"true": "plan_modify", "false": "finalize"},
        )
        g.add_conditional_edges(
            "plan_modify",
            self._is_quiz_submit,
            {"true": "lesson_agent", "false": "finalize"},
        )
        g.add_conditional_edges(
            "lesson_agent",
            self._is_quiz_submit,
            {"true": "quiz_agent", "false": "finalize"},
        )
        g.add_edge("quiz_agent", "finalize")
        g.add_edge("curriculum_agent", "finalize")
        g.add_edge("plan_create", "finalize")
        return g.compile()

    def supervisor_node(self, state: GraphState) -> dict[str, Any]:
        payload = state["payload"]
        intent = state["intent"]

        required = {
            "analyze_curriculum": ["course_id", "document_id"],
            "create_plan": ["student_id", "course_id"],
            "adapt_plan": ["student_id", "course_id"],
            "generate_lesson": ["course_id", "topic_id"],
            "generate_quiz": ["course_id"],
            "quiz_submit": ["attempt_id", "course_id", "student_id"],
            "generate_recommendation": ["student_id", "course_id"],
        }
        missing = [k for k in required.get(intent, []) if not payload.get(k)]
        if missing:
            err = f"Missing required fields for {intent}: {missing}"
            return {"errors": [err], "status": "failed", "context": state.get("context", {})}

        ctx = dict(state.get("context") or {})

        if intent == "quiz_submit":
            # expose attempt_id to the downstream grade/adapt chain
            ctx["quiz_submit"] = {"attempt_id": payload["attempt_id"]}

        log.info("supervisor_route", intent=intent, task_id=state["task_id"])
        return {"context": ctx, "status": "running"}

    def _is_quiz_submit(self, state: GraphState) -> str:
        if state.get("intent") != "quiz_submit":
            return "false"
        # advance => nothing to adapt: short-circuit to finalize
        rec = ((state.get("context") or {}).get("recommendation_agent") or {}).get(
            "recommendation"
        ) or {}
        if rec.get("action") == "advance":
            return "false"
        return "true"

    def _route(self, state: GraphState) -> str:
        if state.get("status") == "failed":
            return "finalize"
        return {
            "analyze_curriculum": "curriculum_agent",
            "create_plan": "plan_create",
            "adapt_plan": "plan_modify",
            "generate_lesson": "lesson_agent",
            "generate_quiz": "quiz_agent",
            "quiz_submit": "grading_agent",
            "generate_recommendation": "recommendation_agent",
        }.get(state["intent"], "finalize")

    def finalize_node(self, state: GraphState) -> dict[str, Any]:
        errors = state.get("errors") or []
        status = "success" if not errors and state.get("context") is not None else "failed"
        return {"status": status, "context": state.get("context", {})}

    def run(
        self,
        intent: str,
        payload: dict[str, Any],
        user_id: str | None,
        task_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        supervisor = Supervisor(self.db)
        if task_id is None:
            task = supervisor.start_task(intent, payload, user_id)
            self.db.commit()  # persist the task so failures remain observable
            task_id, correlation_id = task.task_id, task.correlation_id
        start = time.perf_counter()

        graph = self.compile(intent)
        initial: GraphState = {
            "task_id": task_id,
            "correlation_id": correlation_id,
            "intent": intent,
            "user_id": user_id,
            "payload": payload,
            "context": {},
            "errors": [],
            "status": "running",
        }
        try:
            final = graph.invoke(initial)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            log.error("graph_invoke_failed", task_id=task_id, error=str(exc))
            duration = int((time.perf_counter() - start) * 1000)
            supervisor.finish_task(task_id, "failed", error=str(exc), duration_ms=duration)
            self.db.commit()
            raise RuntimeError(f"Agent pipeline failed: {exc}") from exc

        errors = final.get("errors") or []
        status = "success" if not errors else "failed"
        duration = int((time.perf_counter() - start) * 1000)
        supervisor.finish_task(
            task_id,
            status,
            error="; ".join(errors) if errors else None,
            result=final.get("context") or {},
            duration_ms=duration,
        )
        self.db.commit()
        log.info(
            "supervisor_task_finished",
            task_id=task_id,
            correlation_id=correlation_id,
            status=status,
            duration_ms=duration,
        )
        return {
            "task_id": task_id,
            "correlation_id": correlation_id,
            "status": status,
            "errors": errors,
            "context": final.get("context") or {},
        }
