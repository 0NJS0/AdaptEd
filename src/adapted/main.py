from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database.session import init_db
from .logging.logger import get_logger

log = get_logger("adapted.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info(
        "startup",
        app=settings.app_name,
        env=settings.app_env,
        db=settings.redacted_database_url,
        llm=settings.llm_provider,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from .api.routers import agent as agent_router
    from .api.routers import (
        agent_ops,
        auth,
        courses,
        curriculum,
        lessons,
        logs,
        quizzes,
        students,
        study_plans,
        teacher,
        users,
    )

    app.include_router(auth.router)
    app.include_router(courses.router)
    app.include_router(curriculum.router)
    app.include_router(study_plans.router)
    app.include_router(study_plans.router2)
    app.include_router(lessons.router)
    app.include_router(quizzes.router)
    app.include_router(students.router)
    app.include_router(teacher.router)
    app.include_router(agent_router.router)
    app.include_router(agent_ops.router)
    app.include_router(logs.router)
    app.include_router(users.router)

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
            "db": {
                "mode": "postgres",
                "url": settings.redacted_database_url,
            },
        }

    return app


app = create_app()
