"""Tests for the OBE Mapping Agent's reference data, rules, mapper and extractor.

The centrepiece is an ``OutlineExtraction`` that reproduces the real defects
found in the CSC 2209 (OOAD) outline, asserting the rules engine flags each one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapted.obe import mapping
from adapted.obe import reference as ref
from adapted.obe.document import read_outline_bytes, read_outline_text
from adapted.obe.extractor import extract_outline
from adapted.obe.rules import validate
from adapted.obe.summary import build_summary
from adapted.obe.schema import (
    KPA,
    AssessmentEntry,
    CourseMeta,
    CourseOutcome,
    OutlineExtraction,
    POIndicator,
)


def _ooad_outline() -> OutlineExtraction:
    """CSC 2209 OOAD, encoded with its actual (defective) mappings."""
    return OutlineExtraction(
        course=CourseMeta(code="CSC 2209", title="Object Oriented Analysis and Design"),
        cos=[
            CourseOutcome(
                id="CO1",
                description="Explain the concept of object oriented analysis using UML diagrams.",
                verb="explain",
                bloom_level=5,  # defect: "Explain" is L2, tagged L5
                mapped_pos=["PO-f-2"],
            ),
            CourseOutcome(
                id="CO2",
                description="Design the solution of a complex engineering problem using UML.",
                verb="design",
                bloom_level=6,
                mapped_pos=["PO-f-2"],
            ),
            CourseOutcome(
                id="CO3",
                description="Demonstrate a solution for a complex problem using modelling.",
                verb="demonstrate",
                bloom_level=3,
                mapped_pos=["PO-e-1"],
            ),
            CourseOutcome(
                id="CO4",
                description="Compute the required resources and evaluate software metrics.",
                verb="compute",
                bloom_level=3,
                mapped_pos=["PO-e-1"],  # matrix says PO-e-1 ...
            ),
        ],
        po_indicators=[
            POIndicator(
                id="PO-f-2",
                bloom_domain="cognitive",
                bloom_level=5,
                kpa=KPA(k=["K5", "K7"], p=["P1", "P3", "P7"]),
            ),
            POIndicator(
                id="PO-e-1",
                bloom_domain="cognitive",
                bloom_level=3,
                kpa=KPA(k=["K6"], p=["P1", "P4", "P5"]),
            ),
        ],
        assessment=[
            AssessmentEntry(co_id="CO1", mapped_pos=["PO-f-2"], method="Quiz"),
            AssessmentEntry(co_id="CO2", mapped_pos=["PO-f-2"], method="Mid Term Exam"),
            AssessmentEntry(co_id="CO3", mapped_pos=["PO-e-1"], method="Final Term Exam"),
            # ... but the assessment table says PO-j-2 (conflict) and PO-j-2 is undefined
            AssessmentEntry(co_id="CO4", mapped_pos=["PO-j-2"], method="Quiz"),
        ],
        weekly_cos=["CO1", "CO2", "CO3", "CO4"],
    )


def _codes(report) -> set[str]:
    return {f.code for f in report.findings}


# --- reference -----------------------------------------------------------
def test_verb_classification():
    assert ref.cognitive_level_for_verb("explain") == 2
    assert ref.cognitive_level_for_verb("apply") == 3
    assert ref.cognitive_level_for_verb("design") == 6
    assert ref.level_name("cognitive", 5) == "Evaluating"
    assert ref.cognitive_level_for_verb("floopynoun") is None


def test_po_indicator_validity():
    assert ref.is_valid_po_indicator("PO-a-1")
    assert ref.is_valid_po_indicator("PO-f-2")
    assert not ref.is_valid_po_indicator("PO-z-1")
    assert not ref.is_valid_po_indicator("POa1")
    assert ref.po_family("PO-f-2") == "f"


# --- rules: the OOAD defects --------------------------------------------
def test_ooad_verb_bloom_mismatch():
    report = validate(_ooad_outline())
    mismatches = [f for f in report.findings if f.code == "verb_bloom_mismatch"]
    # CO1 ("Explain" tagged L5) is the mismatch; CO2/3/4 verbs match their levels
    assert any(f.location == "CO1" for f in mismatches)


def test_ooad_cross_table_conflict():
    report = validate(_ooad_outline())
    conflicts = [f for f in report.findings if f.code == "co_po_table_conflict"]
    assert any(f.location == "CO4" for f in conflicts)


def test_ooad_undefined_po():
    report = validate(_ooad_outline())
    undefined = [f for f in report.findings if f.code == "undefined_po"]
    assert any("PO-j-2" in f.message for f in undefined)


def test_ooad_has_errors_and_fails():
    report = validate(_ooad_outline())
    assert report.error_count >= 1
    assert report.passed is False
    # findings are error-first
    assert report.findings[0].severity == "error"


# --- rules: coverage & clean case ---------------------------------------
def test_insufficient_cos():
    ext = OutlineExtraction(cos=[CourseOutcome(id="CO1", description="Only one.")])
    report = validate(ext)
    assert "insufficient_cos" in _codes(report)


def test_clean_outline_passes():
    ext = OutlineExtraction(
        course=CourseMeta(code="CSC 0000", title="Clean"),
        cos=[
            CourseOutcome(id="CO1", description="Define terms.", verb="define",
                          bloom_level=1, mapped_pos=["PO-a-1"]),
            CourseOutcome(id="CO2", description="Apply methods.", verb="apply",
                          bloom_level=3, mapped_pos=["PO-a-1"]),
            CourseOutcome(id="CO3", description="Analyze cases.", verb="analyze",
                          bloom_level=4, mapped_pos=["PO-b-1"]),
            CourseOutcome(id="CO4", description="Design a system.", verb="design",
                          bloom_level=6, mapped_pos=["PO-c-1"]),
        ],
        po_indicators=[
            POIndicator(id="PO-a-1", bloom_level=3, kpa=KPA(k=["K1"])),
            POIndicator(id="PO-b-1", bloom_level=4, kpa=KPA(k=["K2"])),
            POIndicator(id="PO-c-1", bloom_level=6, kpa=KPA(k=["K5"])),
        ],
        assessment=[
            AssessmentEntry(co_id="CO1", mapped_pos=["PO-a-1"], method="Quiz"),
            AssessmentEntry(co_id="CO2", mapped_pos=["PO-a-1"], method="Quiz"),
            AssessmentEntry(co_id="CO3", mapped_pos=["PO-b-1"], method="Mid"),
            AssessmentEntry(co_id="CO4", mapped_pos=["PO-c-1"], method="Final"),
        ],
        weekly_cos=["CO1", "CO2", "CO3", "CO4"],
        weights={"mid": 40, "final": 60},
    )
    report = validate(ext)
    assert report.passed is True
    assert report.error_count == 0


def test_invalid_kpa_code():
    ext = OutlineExtraction(
        cos=[CourseOutcome(id=f"CO{i}", description="x", bloom_level=3,
                           mapped_pos=["PO-a-1"]) for i in range(1, 5)],
        po_indicators=[POIndicator(id="PO-a-1", bloom_level=3, kpa=KPA(k=["K9"]))],
    )
    report = validate(ext)
    assert "invalid_kpa_code" in _codes(report)


def test_weights_not_100():
    ext = OutlineExtraction(
        cos=[CourseOutcome(id=f"CO{i}", description="x", bloom_level=3) for i in range(1, 5)],
        weights={"mid": 40, "final": 50},
    )
    report = validate(ext)
    assert "weights_not_100" in _codes(report)


# --- mapper --------------------------------------------------------------
def test_mapping_suggestion_design():
    s = mapping.suggest_for_description("CO1", "Design a solution for a complex problem.")
    assert s.suggested_bloom_level == 6
    assert s.suggested_bloom_name == "Creating"
    assert "PO-c-1" in s.suggested_pos
    assert "P1" in s.suggested_kpa.p  # "complex" -> P1
    assert s.rationale


def test_mapping_suggestion_apply():
    s = mapping.suggest_for_description("CO2", "Apply number system conversion methods.")
    assert s.suggested_bloom_level == 3
    assert s.suggested_pos  # PO-a signals (number system)


# --- extractor (light smoke test on representative flattened text) -------
def test_extractor_smoke():
    text = (
        "CSC 9999 SAMPLE COURSE SEMESTER: Fall, 2025-2026 3 Credit "
        "By the end of this course, students should be able to: "
        "CO1 Determine components of computer hardware. 3 PO-a-1 "
        "CO2 Explain logic gates and boolean algebra. 2 PO-b-1 "
        "Topics to be covered in the class "
        "Week 1 CO1 Intro Week 2 CO2 Logic "
        "Mapping of PO "
        "PO-a-1 Apply concepts in natural science. Cognitive Level 3 (Applying) K1 "
        "PO-b-1 Identify first principles. Cognitive Level 2 (Understanding) K1 "
        "K, P, A Definitions "
    )
    ext = extract_outline(text)
    assert ext.course.code == "CSC 9999"
    ids = {c.id for c in ext.cos}
    assert {"CO1", "CO2"} <= ids
    co1 = next(c for c in ext.cos if c.id == "CO1")
    assert co1.bloom_level == 3
    assert "PO-A-1" in co1.mapped_pos
    assert {"PO-A-1", "PO-B-1"} <= ext.po_indicator_ids()


# --- document reader (bytes) --------------------------------------------
def test_read_outline_bytes_txt():
    text = read_outline_bytes(b"CO1 Define terms. 1 PO-a-1", "outline.txt")
    assert "CO1" in text
    with pytest.raises(ValueError):
        read_outline_bytes(b"x", "outline.png")


# --- full pipeline end-to-end (extract -> validate -> summarize) ---------
SAMPLE = (
    "CSC 7777 SAMPLE OUTLINE SEMESTER: Fall, 2025-2026 3 Credit "
    "By the end of this course, students should be able to: "
    "CO1 Explain the basics of computing. 4 PO-a-1 "
    "CO2 Apply sorting algorithms to solve problems. 3 PO-a-1 "
    "CO3 Analyze algorithmic complexity of a solution. 4 PO-b-1 "
    "CO4 Design a data structure for a complex engineering problem. 6 PO-b-1 "
    "Topics to be covered in the class "
    "Week 1 CO1 Intro Week 2 CO2 Sorting Week 3 CO3 Complexity Week 4 CO4 Design "
    "Mapping of PO "
    "PO-a-1 Apply knowledge of computing fundamentals. Cognitive Level 3 (Applying) K1 "
    "PO-b-1 Analyse complex problems. Cognitive Level 4 (Analyzing) K3 P1 "
    "K, P, A Definitions "
    "Mapping of CO Assessment Method and Rubric "
    "CO1 Explain the basics of computing. PO-a-1 Quiz Rubric for Quiz "
    "CO2 Apply sorting algorithms to solve problems. PO-a-1 Midterm Written Assessment Rubric for Midterm "
    "CO3 Analyze algorithmic complexity of a solution. PO-b-1 Final term Written Assessment Rubric for Final "
    "CO4 Design a data structure for a complex engineering problem. PO-j-2 Quiz Rubric for Quiz "
)


def test_pipeline_end_to_end():
    ext = extract_outline(SAMPLE)
    assert len(ext.cos) == 4
    report = validate(ext)
    codes = _codes(report)
    # CO4's assessment PO (PO-j-2) is undefined and conflicts with the matrix (PO-b-1)
    assert "undefined_po" in codes
    assert "co_po_table_conflict" in codes
    # "Explain" tagged L4 is a verb/Bloom mismatch
    assert any(f.code == "verb_bloom_mismatch" and f.location == "CO1" for f in report.findings)
    assert report.passed is False
    md = build_summary(ext, report, [mapping.suggest_for_co(c) for c in ext.cos])
    assert "CO-PO Mapping Summary" in md and "PO-j-2" in md.replace("PO-J-2", "PO-j-2")


# --- real AIUB outlines (skipped if the sample corpus is not present) ----
_CORPUS = Path(__file__).resolve().parents[2] / "CO-PO Related Files"
_OOAD = _CORPUS / "CSC 2209 Object Oriented Analysis and Design (Fall_25-26).docx"


@pytest.mark.skipif(not _OOAD.exists(), reason="sample OOAD outline not present")
def test_real_ooad_docx_defects():
    """The real CSC 2209 DOCX reproduces its known defects end-to-end."""
    text = read_outline_text(_OOAD, _OOAD.name)
    ext = extract_outline(text)
    assert len(ext.cos) == 4  # DOCX tables were read (shared parser would miss these)
    report = validate(ext)
    codes = _codes(report)
    assert "undefined_po" in codes  # PO-J-2 referenced but never defined
    assert "co_po_table_conflict" in codes  # CO4: PO-E-1 (matrix) vs PO-J-2 (assessment)
    assert report.error_count >= 2
