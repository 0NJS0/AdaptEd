"""Generate the CO-PO mapping summary for a course outline.

Produces the clear, well-structured write-up required by the brief: how the COs,
POs, Bloom levels and K-P-A were mapped, the methodology, and any issues found —
so the same approach transfers to other courses.

The output is deterministic markdown built from the structured extraction and
validation report; it needs no LLM (so it runs offline). The agent may
optionally pass it through the configured provider for stylistic polish.
"""

from __future__ import annotations

from . import reference as ref
from .schema import MappingSuggestion, OutlineExtraction, ValidationReport


def build_summary(
    ext: OutlineExtraction,
    report: ValidationReport,
    suggestions: list[MappingSuggestion] | None = None,
) -> str:
    course = ext.course
    title = course.title or "this course"
    code = course.code or ""
    lines: list[str] = []

    lines.append(f"# CO-PO Mapping Summary — {code} {title}".strip())
    lines.append("")
    lines.append(
        "This summary explains how the Course Outcomes (COs) of the course are mapped to "
        "Program Outcomes (POs), Bloom's Taxonomy levels and the Knowledge–Problem–Activity "
        "(K-P-A) indicators, following the AIUB CS OBE Manual."
    )
    lines.append("")

    # --- Methodology -----------------------------------------------------
    lines.append("## Mapping methodology")
    lines.append("")
    lines.append(
        "1. **Course Outcomes** — each CO is written with a single leading action verb "
        "that fixes its Bloom's Taxonomy level (e.g. *Explain* → Understanding/L2, "
        "*Apply/Solve* → Applying/L3, *Design/Construct* → Creating/L6)."
    )
    lines.append(
        "2. **Program Outcomes** — each CO is mapped to the PO indicator whose intent it "
        "serves (content and natural-science fundamentals → PO-a/PO-b; design → PO-c; "
        "tools & modelling → PO-e; societal/ethical context → PO-f/PO-g)."
    )
    lines.append(
        "3. **Bloom level** — the declared *Level of Domain* must equal the level implied "
        "by the CO's verb and be compatible with the mapped PO indicator's level."
    )
    lines.append(
        "4. **K-P-A** — the mapped PO indicator carries its Knowledge profile (K1-K8), and, "
        "for complex-engineering-problem outcomes, the relevant Problem attributes (P1-P7) "
        "and Activity attributes (A1-A5)."
    )
    lines.append(
        "5. **Assessment** — every CO is taught in the weekly plan and assessed by a method "
        "with a matching rubric; CO attainment is achieved at 60% of the evaluation marks."
    )
    lines.append("")

    # --- Per-CO mapping table -------------------------------------------
    lines.append("## Course Outcome mapping")
    lines.append("")
    if ext.cos:
        lines.append("| CO | Bloom level | Mapped PO(s) | Action verb |")
        lines.append("|----|-------------|--------------|-------------|")
        for co in ext.cos:
            lvl = ""
            if co.bloom_level is not None:
                name = ref.level_name(co.bloom_domain, co.bloom_level) or ""
                lvl = f"{co.bloom_level} ({name})" if name else str(co.bloom_level)
            pos = ", ".join(co.mapped_pos) if co.mapped_pos else "—"
            lines.append(f"| {co.id} | {lvl or '—'} | {pos} | {co.verb or '—'} |")
        lines.append("")
        for co in ext.cos:
            lines.append(f"- **{co.id}** — {co.description}")
        lines.append("")
    else:
        lines.append("_No Course Outcomes were extracted from the outline._")
        lines.append("")

    # --- PO indicators / K-P-A ------------------------------------------
    if ext.po_indicators:
        lines.append("## PO indicators and K-P-A")
        lines.append("")
        lines.append("| PO indicator | Domain / level | K | P | A |")
        lines.append("|--------------|----------------|---|---|---|")
        for ind in ext.po_indicators:
            dl = ""
            if ind.bloom_level is not None:
                name = ref.level_name(ind.bloom_domain, ind.bloom_level) or ""
                dl = f"{ind.bloom_domain.title()} L{ind.bloom_level} ({name})".strip()
            lines.append(
                f"| {ind.id} | {dl or '—'} | {', '.join(ind.kpa.k) or '—'} "
                f"| {', '.join(ind.kpa.p) or '—'} | {', '.join(ind.kpa.a) or '—'} |"
            )
        lines.append("")

    # --- Validation ------------------------------------------------------
    lines.append("## Validation findings")
    lines.append("")
    if not report.findings:
        lines.append("✅ No issues detected — the mapping is internally consistent.")
    else:
        lines.append(
            f"Detected **{report.error_count} error(s)**, "
            f"**{report.warning_count} warning(s)**, "
            f"**{report.info_count} info** note(s):"
        )
        lines.append("")
        icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}
        for f in report.findings:
            lines.append(f"- {icon.get(f.severity, '•')} **{f.location}** — {f.message}")
            if f.suggestion:
                lines.append(f"  - _Suggested fix:_ {f.suggestion}")
    lines.append("")

    # --- Suggestions -----------------------------------------------------
    if suggestions:
        lines.append("## Suggested mappings")
        lines.append("")
        for s in suggestions:
            lvl = (
                f"L{s.suggested_bloom_level} ({s.suggested_bloom_name})"
                if s.suggested_bloom_level
                else "level unknown"
            )
            pos = ", ".join(s.suggested_pos) if s.suggested_pos else "—"
            lines.append(f"- **{s.co_id or 'CO'}** → Bloom {lvl}; suggested PO(s): {pos}")
            for r in s.rationale:
                lines.append(f"  - {r}")
        lines.append("")

    lines.append("---")
    lines.append(
        "_Generated by the AdaptED OBE Mapping Agent. Mappings are suggestions for faculty "
        "review, grounded in the AIUB CS OBE Manual; the agent does not modify the source "
        "outline._"
    )
    return "\n".join(lines)
