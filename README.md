# AdaptED

**Intelligent Adaptive Education Assistant** — a multi-agent AI platform that
transforms course materials into personalized learning experiences. Teachers
upload textbooks; the system analyzes the curriculum, generates grounded
lessons, creates quizzes, grades submissions, identifies weak topics, and
continuously adapts each student's learning path.

Built with FastAPI, LangGraph, PostgreSQL + pgvector, and Streamlit.
Powered by OpenRouter free models.

## Overview

Traditional education tools deliver the same content to every student. AdaptED
does the opposite: it builds a dynamic model of each student's mastery,
misconceptions, and learning preferences, then uses a chain of specialized AI
agents to continuously adjust what they study, when they study it, and how
deeply they need to review.

The core loop works like this:

1. A teacher uploads a textbook (PDF, DOCX, or Markdown).
2. The system parses, chunks, and embeds the document into a vector store.
3. An LLM extracts the chapter/topic structure, learning objectives, and
   prerequisites — building a curriculum graph.
4. Students receive a personalized study plan ordered by prerequisites.
5. Lessons are generated on demand, grounded in the retrieved curriculum chunks.
6. Quizzes assess understanding across multiple question types.
7. When a student submits answers, a full adaptive chain fires in the
   background: grade -> analyze performance -> recommend -> adapt the plan
   -> generate a remedial lesson -> create a reassessment quiz.

Every step is observable: agent tasks, inter-agent messages, and audit logs are
all persisted in the database.

## Architecture

```
+------------------------------------------------------------------+
|  Streamlit UI  (src/adapted/ui/)                                 |
|  Teacher views: Dashboard, Curriculum, Class, Review, Ops        |
|  Student views: Dashboard, Study Plan, Learn, Quizzes, Progress  |
+------------------------------------------------------------------+
          |  httpx (bearer token)
          v
+------------------------------------------------------------------+
|  FastAPI Backend  (src/adapted/)                                  |
|  12 routers | JWT auth | Pydantic v2 schemas | CORS              |
+------------------------------------------------------------------+
          |
          v
+------------------------------------------------------------------+
|  Agent Orchestration  (agents/ + graph/)                         |
|  LangGraph StateGraph | Supervisor | 7 specialized agents        |
|  Background ThreadPoolExecutor (tasks/runner.py)                 |
+------------------------------------------------------------------+
          |                           |
          v                           v
+------------------+    +----------------------------------------+
| Service Layer    |    | RAG Pipeline  (rag/)                   |
| grading          |    | Parser -> Chunker -> Embeddings        |
| scheduler        |    | -> VectorStore (pgvector) -> Retriever |
| analytics        |    +----------------------------------------+
| mastery          |                    |
+------------------+                    v
          |              +----------------------------------------+
          v              | LLM Providers  (llm/)                  |
+------------------+    | OpenAI-compatible (OpenRouter) | Mock   |
| Data Layer       |    +----------------------------------------+
| PostgreSQL 18.4  |
| pgvector 0.8.6   |
| 29 ORM models    |
+------------------+
```

The system has 9 logical layers:

| Layer | Responsibility |
|-------|---------------|
| **UI** | Streamlit app with role-based teacher/student views |
| **API** | FastAPI routers, JWT auth, request/response schemas |
| **Agent Orchestration** | LangGraph state graph, supervisor routing, background execution |
| **Services** | Grading logic, study plan scheduling, analytics, mastery tracking |
| **RAG Pipeline** | Document parsing, chunking, embedding, vector search, retrieval |
| **LLM Integration** | Provider abstraction (OpenRouter, mock), embedding support |
| **Data** | SQLAlchemy models, PostgreSQL + pgvector, session management |
| **Application Core** | App factory, config, security, structured logging |
| **Config** | Environment variables, pyproject.toml, .env |

## Key Features

- **Curriculum Analysis** — Upload a textbook and the system automatically
  extracts chapters, topics, learning objectives, and prerequisite
  relationships via LLM-powered analysis grounded in the document.

- **RAG-Grounded Lessons** — Lessons are generated on demand, grounded in
  retrieved curriculum chunks with page citations. Supports standard,
  beginner, advanced, and remedial levels. Incorporates each student's
  mastery profile and misconceptions into the generated content.

- **Adaptive Quiz Generation** — Creates MCQ, true/false, numerical,
  short-answer, and problem-type questions. Deduplicates against existing
  question banks. Supports assessment, reassessment, exit ticket, and mini
  quiz types.

- **Automated + Human-in-the-Loop Grading** — Objective questions are graded
  deterministically. Subjective questions receive LLM rubric grading with
  confidence scoring. Low-confidence subjective answers are flagged for
  teacher review.

- **Performance Analysis & Misconception Detection** — Tracks per-topic
  mastery via exponential moving average (alpha=0.4). Detects persistent
  misconceptions: repeated wrong choices and recurring topic errors across
  quiz attempts.

- **Intelligent Study Planning** — Builds study plans with topological
  ordering (prerequisites first). Validates feasibility against deadlines
  and daily time budgets. Adapts plans by inserting review and reassessment
  items for weak topics.

- **Full Adaptive Chain** — Quiz submission triggers a 6-agent pipeline:
  grade -> analyze performance -> recommend -> adapt plan -> generate
  remedial lesson -> create reassessment quiz. Runs asynchronously in a
  background thread pool.

- **Teacher Review Queue** — Shows only low-confidence AI-graded subjective
  answers scoped to the teacher's own courses. Allows score and feedback
  overrides.

- **Class Analytics** — Aggregated topic mastery across students, weak-topic
  identification, per-student grade histories.

- **Async Background Execution** — Lessons, quizzes, and the full adaptive
  chain run in a `ThreadPoolExecutor(max_workers=4)`. The UI polls via an
  auto-refreshing Streamlit fragment with a "being generated" notifier.

- **Mock/Offline Mode** — `LLM_PROVIDER=mock` + `EMBED_PROVIDER=mock` gives
  a fully offline deterministic run with a hardcoded math curriculum and
  question bank. Useful for development and testing.

- **Full Observability** — Every agent task and inter-agent message is
  persisted. Audit logs track all mutations. A stale-task reaper auto-fails
  tasks stuck for more than 60 minutes.

- **Document Management** — Upload PDF, DOCX, TXT, or Markdown files.
  Delete individual documents, clear all course contents, or delete an
  entire course with cascading cleanup.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Web Framework | FastAPI 0.115+ |
| ASGI Server | Uvicorn |
| UI | Streamlit 1.37+ |
| ORM | SQLAlchemy 2.0+ (mapped_column, Mapped) |
| Database | PostgreSQL 18.4 + pgvector 0.8.6 |
| DB Driver | psycopg3 (binary) |
| Vector Search | pgvector cosine similarity (`<=>` operator) |
| LLM Integration | OpenAI SDK 1.40+ (via OpenRouter) |
| Agent Orchestration | LangGraph 0.2+ (StateGraph) |
| Document Parsing | pypdf (PDF), python-docx (DOCX) |
| Embeddings | nvidia/nemotron-3-embed-1b:free (2048-dim, query-aware) |
| Auth | PyJWT (HS256), bcrypt |
| HTTP Client | httpx |
| Data Validation | Pydantic v2 (email, settings) |
| Config | pydantic-settings (.env) |
| Logging | structlog (JSON renderer) |
| Package Manager | uv (with lockfile) |
| Build System | hatchling |
| Linting | ruff (line-length 100, target py312) |

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 15+ with pgvector extension
- [uv](https://docs.astral.sh/uv/) package manager

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set DATABASE_URL
```

Key settings for a minimal working setup:

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/adapted
LLM_PROVIDER=mock
EMBED_PROVIDER=mock
SECRET_KEY=any-random-string-here
```

### 3. Start the backend

```bash
uv run uvicorn adapted.main:app --port 8001
```

The server creates tables and the pgvector extension on first start.
Verify with: `curl localhost:8001/health`

### 4. Start the UI (separate terminal)

```bash
uv run streamlit run src/adapted/ui/app.py
```

Opens at `http://localhost:8501`. The UI talks to the backend on `:8001`
by default (override with `ADAPTED_API_URL`).

### 5. Try it

1. Register a teacher account (email + password + role=teacher)
2. Create a course
3. Upload a textbook (PDF, DOCX, TXT, or Markdown)
4. Run "Analyze Curriculum" on the course
5. Register a student, enroll them in the course
6. Create a study plan, generate a lesson, take a quiz

### Using real LLMs

To use OpenRouter (free models only):

```env
LLM_PROVIDER=openrouter
EMBED_PROVIDER=openrouter
OPENROUTER_API_KEY=your-key-here
```

The default chat model is `openrouter/free` and the default embedding model
is `nvidia/nemotron-3-embed-1b:free` (2048-dim, query-aware). All LLM calls
are bounded by `llm_timeout_seconds=120`.

## Project Layout

```
src/adapted/
  main.py                 FastAPI app factory (create_app) + /health endpoint
  config.py               pydantic-settings — reads .env, exposes Settings singleton

  api/
    deps.py               JWT auth, role guards (TeacherDep, StudentDep),
                          course ownership/enrollment assertions
    routers/
      auth.py             POST /auth/register, /auth/login, GET /auth/me
      courses.py          CRUD courses, upload/delete documents, enroll, delete
      curriculum.py       GET /courses/{id}/curriculum, /topics/{id}
      lessons.py          POST /lessons/generate (async), GET /lessons/{id}
      quizzes.py          POST /quizzes/generate (async), GET /quizzes/{id},
                          POST /quizzes/{id}/submit (async — triggers adaptive chain)
      study_plans.py      GET /study-plans/{sid}/{cid}, /students/{sid}/study-plan
      students.py         GET /students/{sid}/profile|performance|mastery|recommendations
      teacher.py          GET /classes/{cid}/students|analytics|grades,
                          /quizzes/pending-review, PATCH /classes/answers/{id}
      agent.py            POST /agent/run (generic pipeline trigger)
      agent_ops.py        GET /agent/tasks|messages, stale-task reaper
      logs.py             GET /logs/audit (teacher-only)
      users.py            GET /users/search (teacher-only)

  agents/
    base.py               BaseAgent ABC, AgentResult, output validation,
                          output_is_empty retry hook
    supervisor.py         Intent classification, WORKFLOWS mapping, task lifecycle
    message.py            AgentMessage dataclass, MessageBus (persisted hops)
    curriculum_agent.py   Parse document, embed chunks, LLM extract curriculum
    planner_agent.py      Build/adapt study plan (algorithmic, no LLM)
    lesson_agent.py       RAG retrieve + LLM lesson generation
    quiz_agent.py         LLM question generation, dedup, quiz assembly
    grading_agent.py      Objective grading + LLM subjective grading
    performance_agent.py  Mastery update (EMA), misconception detection
    recommendation_agent.py  Decision logic + LLM narrative

  graph/
    runtime.py            LangGraph StateGraph, compile per intent,
                          retry with DB savepoints

  llm/
    base.py               LLMProvider ABC, LLMRequest
    mock.py               MockProvider — deterministic offline responses
    openai_compatible.py  OpenRouter via OpenAI SDK (json_object response)
    registry.py           get_provider(), get_embed_provider() with LRU cache

  rag/
    parser.py             PDF/DOCX/TXT/Markdown parsing
    chunker.py            Heading-aware chunking (~1500 chars, 200 overlap)
    embeddings.py         LRU-cached embed with passage/query mode
    vector_store.py       pgvector search, upsert, delete
    retriever.py          embed query -> search -> return RetrievedChunk objects

  models/
    user.py               User, Teacher, Student
    course.py             Course, Enrollment, Document
    curriculum.py         Chapter, Topic, TopicPrerequisite,
                          LearningObjective, ContentChunk
    learning.py           StudyPlan, StudyPlanItem, Lesson, Question,
                          Quiz, QuizQuestion, QuizAttempt, Answer, Grade
    memory.py             StudentMastery, StudyHistory, Misconception,
                          ConversationMemory, LearningPreference, Recommendation
    observability.py      AgentTask, AgentMessage, AuditLog

  schemas/
    api.py                30+ Pydantic request/response models

  services/
    analytics.py          weak_and_strong(), detect_misconceptions()
    grading.py            question_hash(), grade_objective()
    mastery.py            update_mastery() — exponential moving average
    scheduler.py          build_plan(), adapt_plan(), validate_plan()

  memory/
    curriculum_memory.py  index_document() — chunk + embed + store
    student_memory.py     build_profile(), update_topic_mastery()

  tasks/
    runner.py             ThreadPoolExecutor background runner

  security/
    jwt.py                create_access_token(), decode_access_token()
    passwords.py          hash_password(), verify_password() (bcrypt)

  logging/
    logger.py             structlog configuration

  tools/
    registry.py           Tool registry (rag_retrieve, web_search, etc.)

  ui/
    app.py                Streamlit app — auth, 5 teacher views, 5 student views
    client.py             APIClient (httpx) covering every API endpoint

storage/
  documents/              Uploaded PDFs/docx/txt/md files (git-ignored)
```

## API Reference

All endpoints require a JWT bearer token unless noted. The token is obtained
via `POST /auth/register` or `POST /auth/login`.

### Authentication

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/register` | None | Register a new teacher or student. Returns JWT. |
| `POST` | `/auth/login` | None | Authenticate by email/password. Returns JWT. |
| `GET` | `/auth/me` | Any | Return the current authenticated user. |

### Courses

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/courses` | Teacher | Create a new course. |
| `GET` | `/courses` | Any | List courses (role-scoped). |
| `GET` | `/courses/{id}` | Owner/Enrolled | Get a single course. |
| `POST` | `/courses/{id}/enroll` | Teacher | Enroll a student in a course. |
| `DELETE` | `/courses/{id}` | Teacher | Delete course and all contents. |

### Documents

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/courses/{id}/documents` | Teacher | Upload a document (multipart). |
| `GET` | `/courses/{id}/documents` | Owner/Enrolled | List documents for a course. |
| `GET` | `/courses/{id}/documents/{doc_id}` | Owner/Enrolled | Get document status. |
| `DELETE` | `/courses/{id}/documents/{doc_id}` | Teacher | Delete document and its curriculum. |
| `DELETE` | `/courses/{id}/contents` | Teacher | Clear all course contents (keep shell). |

### Curriculum

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/courses/{id}/curriculum` | Owner/Enrolled | Full curriculum tree: chapters with topics. |
| `GET` | `/courses/{id}/topics/{topic_id}` | Owner/Enrolled | Single topic with objectives and prerequisites. |

### Lessons

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/lessons/generate` | Any | Kick off async lesson generation. Returns `task_id`. |
| `GET` | `/lessons/{id}` | Any | Fetch a generated lesson by ID. |

### Quizzes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/quizzes/generate` | Any | Kick off async quiz generation. Returns `task_id`. |
| `GET` | `/quizzes/{id}` | Any | Fetch a quiz with questions. |
| `POST` | `/quizzes/{id}/submit` | Student | Submit answers, trigger adaptive chain. Returns `task_id`. |

### Study Plans

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/study-plans/{student_id}/{course_id}` | Any | Get latest active plan for student+course. |
| `GET` | `/students/{student_id}/study-plan` | Any | Get latest active plan across all courses. |

### Students

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/students/{id}/profile` | Any | Full profile: mastery, misconceptions, prefs. |
| `GET` | `/students/{id}/performance` | Any | Topic mastery, weak/strong, misconceptions. |
| `GET` | `/students/{id}/mastery` | Any | Overall + per-topic mastery scores. |
| `GET` | `/students/{id}/recommendations` | Any | List recent recommendations. |
| `PATCH` | `/students/{id}/recommendations/{rid}` | Any | Update recommendation status. |
| `POST` | `/students/{id}/preferences` | Any | Set a learning preference key-value. |

### Teacher / Classes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/classes/{cid}/students` | Teacher | List enrolled students. |
| `GET` | `/classes/{cid}/analytics` | Teacher | Class-wide topic mastery and weak topics. |
| `GET` | `/classes/{cid}/students/{sid}/grades` | Teacher | Per-student grade history. |
| `GET` | `/classes/quizzes/pending-review` | Teacher | Low-confidence AI-graded answers (scoped). |
| `PATCH` | `/classes/answers/{aid}` | Teacher | Override AI grade with teacher score/feedback. |

### Agent Operations

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/agent/run` | Any | Trigger any agent pipeline by intent. |
| `GET` | `/agent/tasks` | Any | List recent agent tasks. |
| `GET` | `/agent/tasks/{task_id}` | Any | Get a single task result. |
| `GET` | `/agent/messages` | Any | List inter-agent messages. |

### Users & Logs

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/users/search` | Teacher | Search users by name/email. |
| `GET` | `/logs/audit` | Teacher | List audit log entries. |
| `GET` | `/health` | None | Health check with DB status. |

## Data Models

The system uses 29 ORM models across 6 model files, all backed by PostgreSQL.

### Entity Relationships

```
User (1) --- 1 --- Teacher --- 1 --- (many) Course
  |                                     |
  |                                     +--- Document --- ContentChunk (vector)
  |                                     |     (chapters cascade)
  |                                     |
  |                                     +--- Chapter --- Topic
  |                                                      |--- LearningObjective
  |                                                      |--- TopicPrerequisite (self-ref)
  |
  +--- 1 --- Student
                 |
                 +--- Enrollment --- Course
                 +--- StudyPlan --- StudyPlanItem --- Topic
                 +--- StudentMastery --- Topic
                 +--- StudyHistory
                 +--- Misconception
                 +--- ConversationMemory
                 +--- Recommendation

Course --- Quiz --- QuizQuestion --- Question
           |--- QuizAttempt --- Answer --- Question
                            |--- Grade

AgentTask --- AgentMessage
AuditLog (standalone)
LearningPreference (per User, key-value)
```

### Key Tables

**Identity & Access**

| Table | Purpose |
|-------|---------|
| `users` | Email, password hash, role (teacher/student) |
| `teachers` | FK to user, department |
| `students` | FK to user, grade_level, daily_study_minutes |

**Courses & Content**

| Table | Purpose |
|-------|---------|
| `courses` | Title, subject, teacher_id, exam_date, status |
| `enrollments` | Links students to courses |
| `documents` | Uploaded files with status lifecycle (uploaded->processing->ready) |
| `chapters` | Extracted from documents, ordered |
| `topics` | Within chapters, with difficulty scores |
| `topic_prerequisites` | Self-referencing many-to-many for dependency graph |
| `learning_objectives` | Per-topic objectives extracted by LLM |
| `content_chunks` | RAG chunks with pgvector `vector(2048)` column |

**Learning**

| Table | Purpose |
|-------|---------|
| `study_plans` | Per student+course, versioned on adaptation |
| `study_plan_items` | Day-indexed plan entries linked to topics |
| `lessons` | Generated lesson content (JSON), level, chunks_used |
| `questions` | Question bank with dedup hash, type, choices, difficulty |
| `quizzes` | Collections of questions with quiz_type |
| `quiz_questions` | Join table with position and assigned difficulty |
| `quiz_attempts` | Student submissions, score, status |
| `answers` | Per-question responses with AI grading + teacher override |
| `grades` | Final grade per attempt |

**Memory & Recommendations**

| Table | Purpose |
|-------|---------|
| `student_mastery` | Per-topic mastery (0-100), exponential moving average |
| `study_history` | Activity log (lesson/quiz/practice/review) |
| `misconceptions` | Detected persistent misunderstandings |
| `conversation_memory` | Focus topic tracking |
| `learning_preferences` | Key-value student preferences |
| `recommendations` | Actionable next-step recommendations with status |

**Observability**

| Table | Purpose |
|-------|---------|
| `agent_tasks` | Task lifecycle: started->success/failed, result JSON |
| `agent_messages` | Inter-agent communication hops |
| `audit_logs` | All mutations with user, action, resource, timestamp |

## Agent Framework

### BaseAgent Interface

All agents inherit from `BaseAgent` and implement the `process()` method:

```python
class BaseAgent(ABC):
    name: str
    actions: set[str]
    output_schema: type[BaseModel]

    def process(self, message: AgentMessage) -> dict: ...  # abstract
    def output_is_empty(self, output: dict) -> bool: ...   # retry hook
    def handle(self, message: AgentMessage) -> AgentResult: ...  # template method
```

The `handle()` template method calls `process()`, validates output against
`output_schema`, and records the hop on the `MessageBus`. The `output_is_empty()`
hook enables retry-on-empty: if the LLM returns schema-valid but empty data
(e.g. `{"chapters": []}`), the runtime rolls back and retries.

### The 7 Agents

| Agent | LLM? | Purpose |
|-------|------|---------|
| **CurriculumAnalyzerAgent** | Yes | Parse document, embed chunks, extract chapters/topics/objectives via LLM |
| **StudyPlannerAgent** | No | Build/adapt study plans with topological ordering (algorithmic) |
| **LessonAgent** | Yes | RAG-retrieve curriculum chunks, generate grounded lesson with student profile |
| **QuizAgent** | Yes | Generate questions via LLM, deduplicate by hash, assemble quiz |
| **GradingAgent** | Partial | Grade objective deterministically, subjective via LLM rubric + confidence |
| **PerformanceAnalysisAgent** | No | Update mastery (EMA), detect misconceptions, classify weak/strong topics |
| **RecommendationAgent** | Partial | Decision tree + optional LLM narrative for next-step recommendation |

### Pipeline Composition (LangGraph)

The agents are wired into a LangGraph `StateGraph` with conditional routing.
Each intent compiles a different graph shape:

```
analyze_curriculum:  supervisor -> curriculum_agent -> finalize
create_plan:         supervisor -> plan_create -> finalize
generate_lesson:     supervisor -> lesson_agent -> finalize
generate_quiz:       supervisor -> quiz_agent -> finalize
quiz_submit:         supervisor -> grading -> performance -> recommendation
                     -> plan_modify -> lesson -> reassessment_quiz -> finalize
```

The `quiz_submit` chain is the full adaptive loop. After the recommendation
agent, a conditional gate decides: if the action is "advance" (no weak
topics), the chain short-circuits to finalize. Otherwise it continues through
plan adaptation, remedial lesson generation, and reassessment quiz creation.

### The Adaptive Learning Chain

When `POST /quizzes/{id}/submit` is called:

```
Step 1  Supervisor
        Validates intent, seeds context with attempt_id.

Step 2  GradingAgent
        MCQ/TF/Numerical: deterministic string comparison (confidence=1.0).
        Short Answer/Problem: LLM rubric grading (confidence varies).
        Flags low-confidence subjective answers for teacher review.

Step 3  PerformanceAnalysisAgent
        Updates per-topic mastery via EMA (alpha=0.4).
        Detects misconceptions: repeated wrong choices (2+) or
        recurring topic errors (3+).
        Classifies weak (mastery < 60%) and strong (>= 75%) topics.

Step 4  RecommendationAgent
        Decision: "advance" (no weak topics) or "review_topic" (weak topics).
        Generates an encouraging narrative.

Step 5  [Conditional] StudyPlannerAgent (plan.modify)
        Inserts review/practice/reassess items after weak topics.
        Increments plan version.

Step 6  [Conditional] LessonAgent (lesson.generate, level="remedial")
        RAG-retrieves chunks for the weakest topic.
        Generates a personalized remedial lesson.

Step 7  [Conditional] QuizAgent (quiz.generate, type="reassessment")
        Creates 5 new questions for the weak topic.
```

All 6 agent outputs accumulate in the task's `context` dict, stored as the
task result. The caller polls `GET /agent/tasks/{id}` to retrieve it.

### Retry & Savepoint Logic

Each agent dispatch is wrapped in `_run_with_retry()`:

- Up to 2 attempts with exponential backoff
- Each attempt uses a DB savepoint: on error or empty output, the savepoint
  rolls back (only that agent's writes are lost, not earlier agents' work)
- The `output_is_empty()` hook retries schema-valid but empty LLM payloads

## RAG Pipeline

```
Document (PDF/DOCX/TXT/MD)
  |
  v
Parser (rag/parser.py)
  Extracts text per page -> ParsedDocument
  |
  v
Chunker (rag/chunker.py)
  Heading-aware splitting, ~1500 chars, 200 overlap -> list[Chunk]
  |
  v
Embeddings (rag/embeddings.py)
  LRU-cached (4096 entries), mode-aware (passage vs query)
  Model: nvidia/nemotron-3-embed-1b:free (2048-dim)
  |
  v
VectorStore (rag/vector_store.py)
  pgvector upsert into content_chunks.vector
  Cosine similarity search: 1 - (vector <=> CAST(:query AS vector))
  |
  v
Retriever (rag/retriever.py)
  Embed query (mode="query") -> search -> RetrievedChunk objects
  format_context() for LLM injection with citations
```

The curriculum analyzer indexes chunks during document processing (mode=
"passage"). The lesson agent retrieves them during lesson generation
(mode="query"). The query-aware embedding model produces different vectors
for indexing vs retrieval, improving semantic matching.

## Configuration

All settings are read from the repo-root `.env` file via pydantic-settings.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| **App** | | | |
| `APP_NAME` | str | `AdaptED` | Application name |
| `APP_ENV` | str | `development` | Environment identifier |
| `DEBUG` | bool | `true` | Enable debug logging |
| `SECRET_KEY` | str | `change-me...` | JWT signing key (change in production) |
| `CORS_ORIGINS` | str | `http://localhost:8501,...` | Comma-separated allowed origins |
| `STORAGE_DIR` | str | `./storage` | On-disk document storage path |
| **Database** | | | |
| `DATABASE_URL` | str | (required) | PostgreSQL URL (`postgresql+psycopg://...`) |
| **LLM** | | | |
| `LLM_PROVIDER` | str | `mock` | `mock` or `openrouter` |
| `OPENROUTER_BASE_URL` | str | `https://openrouter.ai/api/v1` | OpenRouter API base |
| `OPENROUTER_API_KEY` | str | `""` | OpenRouter API key (only for real LLM) |
| `LLM_MODEL` | str | `openrouter/free` | Chat model name |
| `LLM_TIMEOUT_SECONDS` | float | `120` | Per-request timeout for chat + embed calls |
| **Embeddings** | | | |
| `EMBED_PROVIDER` | str | `mock` | `mock` or `openrouter` (independent from chat) |
| `EMBED_MODEL` | str | `nvidia/nemotron-3-embed-1b:free` | Embedding model |
| `EMBEDDING_DIM` | int | `2048` | Vector dimension (fixed; pgvector columns are fixed-size) |
| **JWT** | | | |
| `JWT_ALGORITHM` | str | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | int | `720` | Token lifetime (12 hours) |
| **Behavior** | | | |
| `DEFAULT_DAILY_STUDY_MINUTES` | int | `90` | Default for new students |
| `MAX_UPLOAD_BYTES` | int | `52428800` | 50 MB upload limit |
| `RAG_TOP_K` | int | `6` | Default retrieval result count |
| `AGENT_MAX_RETRIES` | int | `2` | Max retry attempts for empty LLM output |
| `AGENT_RETRY_BACKOFF_SECONDS` | float | `0.5` | Delay between retries |

Computed properties (set automatically):
- `redacted_database_url` — masks the password in logs and `/health`
- `cors_origin_list` — parsed comma-separated origins
- `storage_path` — `Path(storage_dir)` (creates directory if needed)

## Development

### Lint Gate

```bash
uv run ruff check src/
uv run ruff format src/ --check
```

Both must pass before any change is committed.

### Mock/Offline Mode

Set both providers to mock in `.env`:

```env
LLM_PROVIDER=mock
EMBED_PROVIDER=mock
```

The mock provider returns deterministic responses: a hardcoded math curriculum
(Algebra, Functions, Quadratic Equations; 7 topics), a question bank, and
n-gram-based embeddings. No API keys or network access required.

### Testing

There is no `test/` directory despite the pytest config. Verification is done
via ad-hoc scripts under `/tmp/opencode/` (wiped on reboot) or against a
running backend. See `AGENTS.md` for current verification patterns.

### UI Development

After any change to `ui/app.py` or `ui/client.py`, the Streamlit process must
be restarted. Streamlit caches imported modules in `sys.modules` for the
process lifetime — stale module references cause runtime errors.

```bash
pkill -f '[s]treamlit'   # the bracket trick prevents self-kill
uv run streamlit run src/adapted/ui/app.py
```

### Starting Services

```bash
# Backend (from repo root)
uv run uvicorn adapted.main:app --port 8001

# UI (separate terminal)
uv run streamlit run src/adapted/ui/app.py
```

The mock backend on `:8002` is used for testing and is NOT running by default.

## Known Caveats

- **pgvector index cap**: pgvector 0.8.6 limits HNSW/IVFFlat indexes to 2000
  dimensions. The Nemotron embedding model is locked at 2048-dim, so
  `content_chunks` has no vector index — search runs a sequential scan. This
  is fine at the current dataset scale.

- **Free model speed**: `openrouter/free` legitimately takes 28-34 minutes for
  large PDFs. This is bounded by `llm_timeout_seconds=120` per call. Slow is
  not stuck — the stale-task reaper waits 60 minutes before marking tasks
  failed.

- **Empty README**: This file was intentionally empty; the real project
  documentation lives in `AGENTS.md` (agent conventions) and `PROGRESS.md`
  (session-by-session work log).

- **No test directory**: Despite `pytest testpaths=["test"]` in pyproject.toml,
  there is no `test/` directory. Tests are verified via scratch scripts.

- **AppTest limitations**: Streamlit's `AppTest` cannot drive inner dialog
  buttons to their clicked state. Dialog confirm paths are verified at API
  level instead.

- **UI module caching**: Streamlit caches modules for the process lifetime.
  Any change to `ui/` files requires a full Streamlit restart.
