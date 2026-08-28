"""OBE Mapping & Compliance Agent.

Helps faculty author AIUB CS course outlines: it extracts the CO / PO / Bloom /
K-P-A structure from an outline, validates it against the OBE Manual rules,
suggests mappings for gaps, and generates the mapping-methodology summary.

It is *non-destructive* — it reports and suggests; it never edits the source
document. All integrity checks are deterministic (offline-capable); the LLM is
used only to optionally polish the summary narrative.

Actions
-------
- ``obe.extract``          -> structured extraction of the outline
- ``obe.validate``         -> extraction + severity-ranked validation report
- ``obe.suggest_mapping``  -> Bloom/PO/K-P-A suggestions for CO description(s)
- ``obe.summarize``        -> extraction + report + suggestions + markdown summary
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from ..logging.logger import get_logger
from ..obe import mapping, rules
from ..obe.extractor import extract_outline
from ..obe.schema import MappingSuggestion, OutlineExtraction
from ..obe.summary import build_summary
from .base import BaseAgent
from .message import AgentMessage

log = get_logger("adapted.agents.obe")


class OBEAgent(BaseAgent):
    name = "obe_agent"
    actions: ClassVar[set[str]] = {
        "obe.extract",
        "obe.validate",
        "obe.suggest_mapping",
        "obe.summarize",
    }
    output_schema = None  # output shape varies per action; validated internally

    def __init__(self, db=None, provider=None, bus=None) -> None:
        super().__init__(bus)
        self.db = db
        self.provider = provider

    # -- dispatch ---------------------------------------------------------
    def process(self, message: AgentMessage) -> dict[str, Any]:
        action = message.action
        payload = message.payload
        if action == "obe.suggest_mapping":
            return self._suggest(payload)

        ext = self._load_extraction(payload)
        if action == "obe.extract":
            return {"extraction": ext.model_dump()}
        if action == "obe.validate":
            report = rules.validate(ext)
            return {"extraction": ext.model_dump(), "report": report.model_dump()}
        if action == "obe.summarize":
            return self._summarize(ext, payload)
        raise ValueError(f"OBEAgent cannot handle action '{action}'")

    # -- input loading ----------------------------------------------------
    def _load_extraction(self, payload: dict[str, Any]) -> OutlineExtraction:
        """Build an OutlineExtraction from (in priority order): a pre-structured
        ``outline`` dict, raw ``outline_text``, or a stored ``document_id``."""
        if payload.get("outline"):
            return OutlineExtraction.model_validate(payload["outline"])
        text = payload.get("outline_text")
        if not text and payload.get("document_id"):
            text = self._read_document(payload["document_id"])
        if not text:
            raise ValueError(
                "OBE agent needs one of: 'outline' (structured), 'outline_text' (raw "
                "text), or 'document_id' (a stored outline document)."
            )
        return extract_outline(text)

    def _read_document(self, document_id: str) -> str:
        if self.db is None:
            raise ValueError("No database session available to load the document.")
        from ..models import Document
        from ..obe.document import read_outline_text

        document = self.db.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document {document_id} not found")
        # Use the OBE table-aware reader (the shared rag.parser drops DOCX tables,
        # where the CO/PO matrices live).
        return read_outline_text(Path(document.storage_path), document.filename)

    # -- actions ----------------------------------------------------------
    def _suggest(self, payload: dict[str, Any]) -> dict[str, Any]:
        suggestions: list[MappingSuggestion] = []
        # accept a list of {id, description} or a single description
        items = payload.get("cos")
        if items:
            for i, item in enumerate(items, start=1):
                cid = str(item.get("id") or f"CO{i}")
                desc = str(item.get("description", ""))
                if desc:
                    suggestions.append(mapping.suggest_for_description(cid, desc))
        elif payload.get("description"):
            cid = str(payload.get("co_id") or "CO1")
            suggestions.append(mapping.suggest_for_description(cid, str(payload["description"])))
        else:
            raise ValueError(
                "obe.suggest_mapping needs 'description' or a 'cos' list of "
                "{id, description} items."
            )
        return {"suggestions": [s.model_dump() for s in suggestions]}

    def _summarize(self, ext: OutlineExtraction, payload: dict[str, Any]) -> dict[str, Any]:
        report = rules.validate(ext)
        suggestions = [mapping.suggest_for_co(co) for co in ext.cos]
        markdown = build_summary(ext, report, suggestions)
        if payload.get("polish") and self.provider is not None and not self.provider.is_mock:
            markdown = self._polish(markdown)
        return {
            "extraction": ext.model_dump(),
            "report": report.model_dump(),
            "suggestions": [s.model_dump() for s in suggestions],
            "summary_markdown": markdown,
        }

    def _polish(self, markdown: str) -> str:
        """Optional LLM pass for stylistic polish; falls back to the raw summary."""
        from ..llm.base import LLMRequest

        schema = {
            "type": "object",
            "properties": {"markdown": {"type": "string"}},
            "required": ["markdown"],
        }
        request = LLMRequest(
            task="obe_summary_polish",
            prompt=(
                "Improve the clarity and flow of the following OBE CO-PO mapping summary "
                "without changing any facts, mappings, findings, or figures. Return JSON "
                "with a single 'markdown' field.\n\n" + markdown
            ),
            schema=schema,
            meta={"markdown": markdown},
        )
        try:
            result = self.provider.generate(request)
            return str(result.get("markdown") or markdown)
        except Exception:  # noqa: BLE001
            return markdown
