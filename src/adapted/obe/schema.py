"""Structured schema for OBE outline extraction, validation and mapping.

These models are the contract between the extractor, the rules engine, the
mapper and the OBE agent. They mirror the AIUB CS course-plan template.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["error", "warning", "info"]


class KPA(BaseModel):
    """Knowledge / Problem / Activity indicator codes attached to a PO indicator."""

    k: list[str] = Field(default_factory=list)
    p: list[str] = Field(default_factory=list)
    a: list[str] = Field(default_factory=list)


class CourseOutcome(BaseModel):
    id: str  # "CO1"
    description: str
    verb: str = ""  # leading action verb, filled by the extractor
    bloom_domain: str = "cognitive"  # cognitive | psychomotor | affective
    bloom_level: int | None = None  # 1..6 (declared "Level of Domain")
    mapped_pos: list[str] = Field(default_factory=list)  # ["PO-a-1", ...]


class POIndicator(BaseModel):
    id: str  # "PO-a-1"
    definition: str = ""
    bloom_domain: str = "cognitive"
    bloom_level: int | None = None
    kpa: KPA = Field(default_factory=KPA)


class AssessmentEntry(BaseModel):
    co_id: str
    mapped_pos: list[str] = Field(default_factory=list)
    method: str = ""  # Quiz, Midterm Written Assessment, Project, ...
    rubric: str = ""


class CourseMeta(BaseModel):
    code: str = ""
    title: str = ""
    semester: str = ""
    credit: str = ""


class OutlineExtraction(BaseModel):
    """Everything the agent pulls out of a single course outline."""

    course: CourseMeta = Field(default_factory=CourseMeta)
    cos: list[CourseOutcome] = Field(default_factory=list)
    po_indicators: list[POIndicator] = Field(default_factory=list)
    assessment: list[AssessmentEntry] = Field(default_factory=list)
    weekly_cos: list[str] = Field(default_factory=list)  # CO ids referenced in the weekly plan
    weights: dict[str, float] = Field(default_factory=dict)  # {"mid": 40, "final": 60}

    def po_indicator_ids(self) -> set[str]:
        return {p.id.upper() for p in self.po_indicators}


class Finding(BaseModel):
    severity: Severity
    code: str  # machine-readable rule id, e.g. "verb_bloom_mismatch"
    location: str  # where in the outline, e.g. "CO1"
    message: str
    suggestion: str = ""


class ValidationReport(BaseModel):
    course_code: str = ""
    findings: list[Finding] = Field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    passed: bool = True

    def finalize(self) -> ValidationReport:
        self.error_count = sum(f.severity == "error" for f in self.findings)
        self.warning_count = sum(f.severity == "warning" for f in self.findings)
        self.info_count = sum(f.severity == "info" for f in self.findings)
        self.passed = self.error_count == 0
        return self


class MappingSuggestion(BaseModel):
    co_id: str = ""
    description: str = ""
    verb: str = ""
    suggested_domain: str = "cognitive"
    suggested_bloom_level: int | None = None
    suggested_bloom_name: str = ""
    suggested_pos: list[str] = Field(default_factory=list)
    suggested_kpa: KPA = Field(default_factory=KPA)
    rationale: list[str] = Field(default_factory=list)


class OBESummary(BaseModel):
    course_code: str = ""
    markdown: str = ""


class AuthoredCO(BaseModel):
    """A freshly generated, OBE-compliant Course Outcome."""

    id: str
    description: str
    verb: str = ""
    bloom_level: int | None = None
    bloom_name: str = ""
    suggested_pos: list[str] = Field(default_factory=list)
    suggested_kpa: KPA = Field(default_factory=KPA)
    rationale: list[str] = Field(default_factory=list)


class ImprovedCO(BaseModel):
    """A rewritten Course Outcome with the changes made and why."""

    co_id: str = "CO1"
    original_description: str = ""
    improved_description: str = ""
    verb: str = ""
    bloom_level: int | None = None
    bloom_name: str = ""
    suggested_pos: list[str] = Field(default_factory=list)
    suggested_kpa: KPA = Field(default_factory=KPA)
    changes: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
