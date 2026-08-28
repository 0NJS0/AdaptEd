from __future__ import annotations

import os

import httpx


class APIError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class APIClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("ADAPTED_API_URL", "http://localhost:8001")).rstrip(
            "/"
        )
        self.token: str | None = None
        self._client = httpx.Client(timeout=120.0)

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _raise(self, resp: httpx.Response) -> None:
        detail = resp.text
        try:
            body = resp.json()
            detail = body.get("detail", detail)
            if isinstance(detail, list):
                detail = "; ".join(d.get("msg", str(d)) for d in detail)
        except Exception:  # noqa: S110, BLE001
            pass
        raise APIError(resp.status_code, str(detail))

    # ------------------------------------------------------------------ auth
    def register(
        self,
        email: str,
        password: str,
        full_name: str,
        role: str,
        daily_study_minutes: int | None = None,
    ) -> dict:
        body = {
            "email": email,
            "password": password,
            "full_name": full_name,
            "role": role,
            "daily_study_minutes": daily_study_minutes,
        }
        resp = self._client.post(f"{self.base_url}/auth/register", json=body)
        if resp.status_code >= 400:
            self._raise(resp)
        data = resp.json()
        self.token = data["access_token"]
        return data

    def login(self, email: str, password: str) -> dict:
        resp = self._client.post(
            f"{self.base_url}/auth/login", json={"email": email, "password": password}
        )
        if resp.status_code >= 400:
            self._raise(resp)
        data = resp.json()
        self.token = data["access_token"]
        return data

    def me(self) -> dict:
        return self._get("/auth/me")

    def health(self) -> dict:
        resp = self._client.get(f"{self.base_url}/health")
        if resp.status_code >= 400:
            self._raise(resp)
        return resp.json()

    def search_users(self, q: str, role: str | None = "student", limit: int = 20) -> list[dict]:
        params = {"q": q, "limit": limit}
        if role:
            params["role"] = role
        return self._get("/users/search", params=params)

    # ---------------------------------------------------------------- courses
    def create_course(
        self, title: str, subject: str | None, description: str | None, exam_date: str | None
    ) -> dict:
        body = {
            "title": title,
            "subject": subject,
            "description": description,
            "exam_date": exam_date,
        }
        return self._post("/courses", json=body)

    def list_courses(self) -> list[dict]:
        return self._get("/courses")

    def get_course(self, course_id: str) -> dict:
        return self._get(f"/courses/{course_id}")

    def enroll(self, course_id: str, student_id: str) -> dict:
        return self._post(f"/courses/{course_id}/enroll", json={"student_id": student_id})

    def upload_document(
        self, course_id: str, filename: str, content: bytes, content_type: str
    ) -> dict:
        resp = self._client.post(
            f"{self.base_url}/courses/{course_id}/documents",
            headers=self._headers(),
            files={"file": (filename, content, content_type)},
        )
        if resp.status_code >= 400:
            self._raise(resp)
        return resp.json()

    def list_documents(self, course_id: str) -> list[dict]:
        return self._get(f"/courses/{course_id}/documents")

    def document_status(self, course_id: str, document_id: str) -> dict:
        return self._get(f"/courses/{course_id}/documents/{document_id}")

    def delete_document(self, course_id: str, document_id: str) -> dict:
        return self._delete(f"/courses/{course_id}/documents/{document_id}")

    def clear_course_contents(self, course_id: str) -> dict:
        return self._delete(f"/courses/{course_id}/contents")

    def delete_course(self, course_id: str) -> dict:
        return self._delete(f"/courses/{course_id}")

    # ------------------------------------------------------------ curriculum
    def curriculum(self, course_id: str) -> dict:
        return self._get(f"/courses/{course_id}/curriculum")

    def topic(self, course_id: str, topic_id: str) -> dict:
        return self._get(f"/courses/{course_id}/topics/{topic_id}")

    # ------------------------------------------------------------ agent/ops
    def run_agent(self, intent: str, payload: dict) -> dict:
        return self._post("/agent/run", json={"intent": intent, "payload": payload})

    def get_task(self, task_id: str) -> dict:
        return self._get(f"/agent/tasks/{task_id}")

    def agent_tasks(self, limit: int = 50, workflow: str | None = None) -> list[dict]:
        params = {"limit": limit}
        if workflow:
            params["workflow"] = workflow
        return self._get("/agent/tasks", params=params)

    def agent_messages(self, task_id: str | None = None, limit: int = 100) -> list[dict]:
        params = {"limit": limit}
        if task_id:
            params["task_id"] = task_id
        return self._get("/agent/messages", params=params)

    def audit_logs(self, limit: int = 100) -> list[dict]:
        return self._get("/logs/audit", params={"limit": limit})

    # ---------------------------------------------------------------- lessons
    def generate_lesson(
        self, course_id: str, topic_id: str, student_id: str | None = None, level: str = "standard"
    ) -> dict:
        body = {
            "course_id": course_id,
            "topic_id": topic_id,
            "student_id": student_id,
            "level": level,
        }
        return self._post("/lessons/generate", json=body)

    def get_lesson(self, lesson_id: str) -> dict:
        return self._get(f"/lessons/{lesson_id}")

    # ---------------------------------------------------------------- quizzes
    def generate_quiz(
        self,
        course_id: str,
        topic_id: str | None = None,
        student_id: str | None = None,
        count: int = 5,
        difficulty: float = 0.5,
        quiz_type: str = "assessment",
        title: str | None = None,
    ) -> dict:
        body = {
            "course_id": course_id,
            "topic_id": topic_id,
            "student_id": student_id,
            "count": count,
            "difficulty": difficulty,
            "quiz_type": quiz_type,
            "title": title,
        }
        return self._post("/quizzes/generate", json=body)

    def get_quiz(self, quiz_id: str) -> dict:
        return self._get(f"/quizzes/{quiz_id}")

    def submit_quiz(self, quiz_id: str, answers: dict) -> dict:
        return self._post(f"/quizzes/{quiz_id}/submit", json={"answers": answers})

    # ------------------------------------------------------------ study plans
    def study_plan(self, student_id: str, course_id: str) -> dict:
        return self._get(f"/study-plans/{student_id}/{course_id}")

    def latest_study_plan(self, student_id: str) -> dict:
        return self._get(f"/students/{student_id}/study-plan")

    # --------------------------------------------------------------- students
    def student_profile(self, student_id: str) -> dict:
        return self._get(f"/students/{student_id}/profile")

    def student_performance(self, student_id: str) -> dict:
        return self._get(f"/students/{student_id}/performance")

    def student_mastery(self, student_id: str) -> dict:
        return self._get(f"/students/{student_id}/mastery")

    def recommendations(self, student_id: str) -> list[dict]:
        return self._get(f"/students/{student_id}/recommendations")

    def update_recommendation(self, student_id: str, recommendation_id: str, status: str) -> dict:
        return self._patch(
            f"/students/{student_id}/recommendations/{recommendation_id}", json={"status": status}
        )

    def set_preference(self, student_id: str, key: str, value: str) -> dict:
        return self._post(f"/students/{student_id}/preferences", json={"key": key, "value": value})

    # ----------------------------------------------------------------- teacher
    def class_students(self, course_id: str) -> list[dict]:
        return self._get(f"/classes/{course_id}/students")

    def class_analytics(self, course_id: str) -> dict:
        return self._get(f"/classes/{course_id}/analytics")

    def student_grades(self, course_id: str, student_id: str) -> list[dict]:
        return self._get(f"/classes/{course_id}/students/{student_id}/grades")

    def pending_review(self) -> list[dict]:
        return self._get("/classes/quizzes/pending-review")

    def override_grade(
        self,
        answer_id: str,
        score: float | None = None,
        feedback: str | None = None,
        is_correct: bool | None = None,
    ) -> dict:
        body: dict = {}
        if score is not None:
            body["score"] = score
        if feedback is not None:
            body["feedback"] = feedback
        if is_correct is not None:
            body["is_correct"] = is_correct
        return self._patch(f"/classes/answers/{answer_id}", json=body)

    # --------------------------------------------------------------------- OBE
    def analyze_obe(
        self, filename: str, content: bytes, content_type: str, polish: bool = False
    ) -> dict:
        resp = self._client.post(
            f"{self.base_url}/obe/analyze",
            headers=self._headers(),
            files={"file": (filename, content, content_type)},
            data={"polish": str(polish).lower()},
        )
        if resp.status_code >= 400:
            self._raise(resp)
        return resp.json()

    def suggest_obe(self, description: str, co_id: str | None = None) -> dict:
        return self._post("/obe/suggest", json={"description": description, "co_id": co_id})

    # ----------------------------------------------------------------- helpers
    def _get(self, path: str, params: dict | None = None) -> object:
        resp = self._client.get(f"{self.base_url}{path}", headers=self._headers(), params=params)
        if resp.status_code >= 400:
            self._raise(resp)
        return resp.json()

    def _post(self, path: str, json: dict | None = None) -> object:
        resp = self._client.post(f"{self.base_url}{path}", headers=self._headers(), json=json)
        if resp.status_code >= 400:
            self._raise(resp)
        return resp.json()

    def _patch(self, path: str, json: dict | None = None) -> object:
        resp = self._client.patch(f"{self.base_url}{path}", headers=self._headers(), json=json)
        if resp.status_code >= 400:
            self._raise(resp)
        return resp.json()

    def _delete(self, path: str) -> object:
        resp = self._client.delete(f"{self.base_url}{path}", headers=self._headers())
        if resp.status_code >= 400:
            self._raise(resp)
        return resp.json()
