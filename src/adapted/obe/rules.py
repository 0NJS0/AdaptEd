"""Deterministic OBE validation rules.

Every hard integrity verdict (broken mapping, undefined PO, cross-table
conflict, weak coverage) is computed here without any LLM, so results are
reproducible and unit-testable. The LLM is used only for *suggestions* and
*narrative* elsewhere — never for these pass/fail checks.

Each rule takes an ``OutlineExtraction`` and returns a list of ``Finding``.
"""

from __future__ import annotations

from . import reference as ref
from .schema import Finding, OutlineExtraction, ValidationReport

MIN_COS = 4


def _mentions_complex(text: str) -> bool:
    low = text.lower()
    return any(sig in low for sig in ref.COMPLEX_PROBLEM_SIGNALS)


def coverage_rule(ext: OutlineExtraction) -> list[Finding]:
    """FR-5 — enough COs, a spread of Bloom levels, and every CO taught & assessed."""
    findings: list[Finding] = []

    if len(ext.cos) < MIN_COS:
        findings.append(
            Finding(
                severity="error",
                code="insufficient_cos",
                location="outline",
                message=f"Only {len(ext.cos)} CO(s) found; the OBE template requires "
                f"at least {MIN_COS}.",
                suggestion=f"Add at least {MIN_COS - len(ext.cos)} more Course Outcome(s).",
            )
        )

    levels = {co.bloom_level for co in ext.cos if co.bloom_level is not None}
    if ext.cos and len(levels) == 1:
        (only,) = tuple(levels)
        findings.append(
            Finding(
                severity="warning",
                code="no_bloom_spread",
                location="outline",
                message=f"All COs sit at Bloom level {only}; outcomes normally span a "
                f"range of cognitive levels.",
                suggestion="Introduce higher-order outcomes (analyse / evaluate / create) "
                "so the course is not confined to one level.",
            )
        )

    weekly = {c.upper() for c in ext.weekly_cos}
    assessed = {a.co_id.upper() for a in ext.assessment}
    for co in ext.cos:
        cid = co.id.upper()
        if weekly and cid not in weekly:
            findings.append(
                Finding(
                    severity="warning",
                    code="co_not_in_weekly_plan",
                    location=co.id,
                    message=f"{co.id} is never referenced in the weekly plan.",
                    suggestion=f"Map {co.id} to at least one week of teaching.",
                )
            )
        if assessed and cid not in assessed:
            findings.append(
                Finding(
                    severity="error",
                    code="co_not_assessed",
                    location=co.id,
                    message=f"{co.id} has no assessment method / rubric.",
                    suggestion=f"Assign an assessment method and rubric to {co.id}.",
                )
            )
        if co.bloom_level is None:
            findings.append(
                Finding(
                    severity="warning",
                    code="missing_bloom_level",
                    location=co.id,
                    message=f"{co.id} has no declared Bloom (Level of Domain) value.",
                    suggestion="State the Bloom level (1-6) for this outcome.",
                )
            )
    return findings


def verb_bloom_rule(ext: OutlineExtraction) -> list[Finding]:
    """FR-2 — the CO's leading action verb must match its declared Bloom level."""
    findings: list[Finding] = []
    for co in ext.cos:
        if not co.verb or co.bloom_level is None or co.bloom_domain != "cognitive":
            continue
        inferred = ref.cognitive_level_for_verb(co.verb)
        if inferred is None:
            continue
        if inferred != co.bloom_level:
            declared_name = ref.level_name("cognitive", co.bloom_level) or "?"
            inferred_name = ref.level_name("cognitive", inferred) or "?"
            findings.append(
                Finding(
                    severity="warning",
                    code="verb_bloom_mismatch",
                    location=co.id,
                    message=f"{co.id} verb “{co.verb}” is Bloom level {inferred} "
                    f"({inferred_name}), but the outcome is tagged level "
                    f"{co.bloom_level} ({declared_name}).",
                    suggestion=f"Either change the level to {inferred} ({inferred_name}) "
                    f"or reword the CO with a level-{co.bloom_level} "
                    f"({declared_name}) verb.",
                )
            )
    return findings


def po_defined_rule(ext: OutlineExtraction) -> list[Finding]:
    """FR-3 — every PO a CO maps to must be well-formed and defined in the outline."""
    findings: list[Finding] = []
    defined = ext.po_indicator_ids()
    for co in ext.cos:
        for po in co.mapped_pos:
            po_u = po.upper()
            if not ref.is_valid_po_indicator(po):
                findings.append(
                    Finding(
                        severity="error",
                        code="malformed_po",
                        location=co.id,
                        message=f"{co.id} references “{po}”, which is not a valid "
                        f"PO indicator id (expected form PO-<a..l>-<n>).",
                        suggestion="Correct the PO indicator id to a defined family (a-l).",
                    )
                )
                continue
            if defined and po_u not in defined:
                findings.append(
                    Finding(
                        severity="error",
                        code="undefined_po",
                        location=co.id,
                        message=f"{co.id} maps to {po}, but {po} is never defined in the "
                        f"PO / K-P-A indicator table.",
                        suggestion=f"Add a definition row for {po}, or map {co.id} to a "
                        f"defined indicator.",
                    )
                )
    return findings


def domain_compat_rule(ext: OutlineExtraction) -> list[Finding]:
    """FR-3 — a CO's Bloom level should be compatible with its PO indicator's level."""
    findings: list[Finding] = []
    by_id = {p.id.upper(): p for p in ext.po_indicators}
    for co in ext.cos:
        if co.bloom_level is None or co.bloom_domain != "cognitive":
            continue
        for po in co.mapped_pos:
            ind = by_id.get(po.upper())
            if ind is None or ind.bloom_level is None or ind.bloom_domain != "cognitive":
                continue
            if co.bloom_level > ind.bloom_level + 1:
                findings.append(
                    Finding(
                        severity="warning",
                        code="co_exceeds_po_level",
                        location=co.id,
                        message=f"{co.id} is Bloom level {co.bloom_level} but its "
                        f"indicator {po} is only level {ind.bloom_level}; the "
                        f"outcome claims more than the PO indicator supports.",
                        suggestion=f"Align {co.id} with {po}'s level, or map it to a "
                        f"higher-level indicator.",
                    )
                )
    return findings


def kpa_valid_rule(ext: OutlineExtraction) -> list[Finding]:
    """FR-3 — K/P/A codes must be valid, and complex-problem COs need P-attributes."""
    findings: list[Finding] = []
    by_id = {p.id.upper(): p for p in ext.po_indicators}

    for ind in ext.po_indicators:
        for code in ind.kpa.k:
            if code.upper() not in ref.VALID_K:
                findings.append(_bad_code(ind.id, code, "K"))
        for code in ind.kpa.p:
            if code.upper() not in ref.VALID_P:
                findings.append(_bad_code(ind.id, code, "P"))
        for code in ind.kpa.a:
            if code.upper() not in ref.VALID_A:
                findings.append(_bad_code(ind.id, code, "A"))

    for co in ext.cos:
        if not _mentions_complex(co.description):
            continue
        has_p = False
        for po in co.mapped_pos:
            ind = by_id.get(po.upper())
            if ind and ind.kpa.p:
                has_p = True
                break
        if not has_p:
            findings.append(
                Finding(
                    severity="warning",
                    code="complex_without_p",
                    location=co.id,
                    message=f"{co.id} describes a complex engineering problem but none of "
                    f"its PO indicators carry any P (complex-problem) attribute.",
                    suggestion="Attach the relevant P1-P7 attribute(s) to the mapped "
                    "indicator, or soften the CO wording.",
                )
            )
    return findings


def _bad_code(po_id: str, code: str, kind: str) -> Finding:
    return Finding(
        severity="error",
        code="invalid_kpa_code",
        location=po_id,
        message=f"{po_id} declares unknown {kind} indicator “{code}”.",
        suggestion=f"Use a valid {kind} code from the OBE Manual.",
    )


def cross_table_rule(ext: OutlineExtraction) -> list[Finding]:
    """FR-4 — the CO matrix and the assessment/rubric table must agree on each CO."""
    findings: list[Finding] = []
    co_pos = {co.id.upper(): {p.upper() for p in co.mapped_pos} for co in ext.cos}
    co_ids = set(co_pos)
    defined = ext.po_indicator_ids()

    for entry in ext.assessment:
        cid = entry.co_id.upper()
        # a PO cited only in the assessment table must still be defined
        for po in entry.mapped_pos:
            if defined and ref.is_valid_po_indicator(po) and po.upper() not in defined:
                findings.append(
                    Finding(
                        severity="error",
                        code="undefined_po",
                        location=entry.co_id,
                        message=f"The assessment table maps {entry.co_id} to {po}, which is "
                        f"never defined in the PO / K-P-A indicator table.",
                        suggestion=f"Define {po}, or map {entry.co_id} to a defined indicator.",
                    )
                )
        if cid not in co_ids:
            findings.append(
                Finding(
                    severity="error",
                    code="assessment_unknown_co",
                    location=entry.co_id,
                    message=f"The assessment table lists {entry.co_id}, which is not in "
                    f"the CO matrix.",
                    suggestion="Add the CO to the matrix, or remove the stray assessment row.",
                )
            )
            continue
        matrix_pos = co_pos[cid]
        entry_pos = {p.upper() for p in entry.mapped_pos}
        if entry_pos and matrix_pos and entry_pos != matrix_pos:
            findings.append(
                Finding(
                    severity="error",
                    code="co_po_table_conflict",
                    location=entry.co_id,
                    message=f"{entry.co_id} maps to {sorted(matrix_pos)} in the CO matrix "
                    f"but {sorted(entry_pos)} in the assessment table.",
                    suggestion="Make the PO mapping identical in both tables.",
                )
            )
    return findings


def weighting_rule(ext: OutlineExtraction) -> list[Finding]:
    """FR-5 — term weightings should total 100%."""
    if not ext.weights:
        return []
    total = sum(ext.weights.values())
    if abs(total - 100.0) > 0.5:
        return [
            Finding(
                severity="warning",
                code="weights_not_100",
                location="grading",
                message=f"Term weightings total {total:g}%, not 100%.",
                suggestion="Adjust the Mid/Final weightings to sum to 100%.",
            )
        ]
    return []


ALL_RULES = (
    coverage_rule,
    verb_bloom_rule,
    po_defined_rule,
    domain_compat_rule,
    kpa_valid_rule,
    cross_table_rule,
    weighting_rule,
)


def validate(ext: OutlineExtraction) -> ValidationReport:
    """Run every rule and return a severity-ranked report."""
    report = ValidationReport(course_code=ext.course.code)
    for rule in ALL_RULES:
        report.findings.extend(rule(ext))
    order = {"error": 0, "warning": 1, "info": 2}
    report.findings.sort(key=lambda f: order.get(f.severity, 3))
    return report.finalize()
