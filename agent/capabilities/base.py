"""Capability Controller primitives.

Capabilities sit between Task Controller and tools:

  Task Controller → Capability → Tools

A capability owns strategy and state for a goal-oriented operation
(e.g. locate a file). The LLM chooses *what* needs to happen; the
capability decides *how*, calling tools and optionally an LLM only
where judgment is required.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SelectedMetadataSpec:
    """Core contract for structured metadata returned with a selected result."""

    required_fields: Tuple[str, ...] = ()
    strongly_expected_fields: Tuple[str, ...] = ()
    optional_fields: Tuple[str, ...] = ()
    at_least_one_of: Tuple[Tuple[str, ...], ...] = ()
    missing_field_policy: str = "report"  # report | downgrade


@dataclass
class CapabilityResult:
    """Structured result returned to Task Controller / tool facade."""

    status: str  # success | partial | failed | needs_input
    output: Any = None
    confidence: float = 0.0
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    observations: List[Dict[str, Any]] = field(default_factory=list)
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    unresolved_questions: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    capability: str = ""
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def format_context_block(self) -> str:
        """Compact block for injection into the user-turn context."""
        lines = [
            f"[{self.capability or 'Capability'}]",
            f"status: {self.status}",
            f"confidence: {round(self.confidence, 3)}",
        ]
        if self.message:
            lines.append(f"message: {self.message}")
        if self.artifacts:
            lines.append("selected/artifacts:")
            for a in self.artifacts[:5]:
                lines.append(f"  - {a}")
        if self.output and isinstance(self.output, dict):
            selected = self.output.get("selected")
            if isinstance(selected, dict):
                lines.append("selected:")
                for key in ("title", "url", "published_at", "views", "channel", "author", "caption", "query"):
                    value = selected.get(key)
                    if value:
                        lines.append(f"  - {key}: {value}")
            cands = self.output.get("candidates") or []
            if cands and not self.artifacts:
                lines.append("candidates:")
                for c in cands[:5]:
                    if isinstance(c, dict):
                        label = c.get("path") or c.get("url") or c.get("title")
                        if label:
                            lines.append(
                                f"  - {label} (conf={c.get('confidence')})"
                            )
        if self.evidence:
            lines.append("evidence:")
            for e in self.evidence[:5]:
                if isinstance(e, dict):
                    lines.append(f"  - {e}")
                else:
                    lines.append(f"  - {e}")
        if self.unresolved_questions:
            lines.append("unresolved:")
            for q in self.unresolved_questions[:3]:
                lines.append(f"  - {q}")
        if self.status == "success" and self.artifacts:
            if (self.capability or "") == "latest_media":
                lines.append(
                    "Next: answer with the selected URL and include title, "
                    "published_at, views, and caption when available. Do not "
                    "replace the selected result with a playlist or channel page."
                )
            else:
                lines.append(
                    "Next: open the selected path with read_file (or OCR skill). "
                    "Do NOT run raw search_files / terminal find-grep loops."
                )
        elif self.status in {"partial", "failed"}:
            lines.append(
                "Next: if the user asks to dig deeper, one narrow search_files "
                "pass is allowed; otherwise report the gap."
            )
        return "\n".join(lines)


@dataclass
class CapabilityContext:
    """Runtime context passed into Capability.execute."""

    objective: str
    session_id: str = ""
    task_id: str = "default"
    budget: Dict[str, int] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)


class Capability(ABC):
    """Goal-oriented executable unit above primitive tools."""

    name: str = "capability"
    description: str = ""
    required_tools: List[str] = []
    selected_metadata_spec: Optional[SelectedMetadataSpec] = None

    @abstractmethod
    def execute(self, ctx: CapabilityContext) -> CapabilityResult:
        """Run the capability policy; return a structured result."""

    def execute_objective(
        self,
        objective: str,
        *,
        session_id: str = "",
        task_id: str = "default",
        budget: Optional[Dict[str, int]] = None,
        **extras: Any,
    ) -> CapabilityResult:
        result = self.execute(
            CapabilityContext(
                objective=objective,
                session_id=session_id,
                task_id=task_id,
                budget=dict(budget or {}),
                extras=dict(extras),
            )
        )
        return self._finalize_result(result)

    def _finalize_result(self, result: CapabilityResult) -> CapabilityResult:
        spec = self.selected_metadata_spec
        if spec is None or not isinstance(result.output, dict):
            return result
        selected = result.output.get("selected")
        if not isinstance(selected, dict):
            return result

        missing_required = [
            field for field in spec.required_fields if not selected.get(field)
        ]
        missing_expected = [
            field for field in spec.strongly_expected_fields if not selected.get(field)
        ]
        unmet_groups = [
            list(group)
            for group in spec.at_least_one_of
            if not any(selected.get(field) for field in group)
        ]

        if missing_required or missing_expected or unmet_groups:
            result.observations.append(
                {
                    "step": "metadata_assertions",
                    "missing_required": list(missing_required),
                    "missing_expected": list(missing_expected),
                    "unmet_groups": list(unmet_groups),
                }
            )

        if missing_required:
            result.unresolved_questions.append(
                "Selected result is missing required metadata: "
                + ", ".join(missing_required)
            )
            if spec.missing_field_policy == "downgrade" and result.status == "success":
                result.status = "partial"
                result.message = (
                    (result.message + " " if result.message else "")
                    + "Selected result is missing required metadata."
                ).strip()

        if missing_expected:
            result.unresolved_questions.append(
                "Selected result is missing strongly expected metadata: "
                + ", ".join(missing_expected)
            )

        for group in unmet_groups:
            result.unresolved_questions.append(
                "Selected result should include at least one of: "
                + ", ".join(group)
            )

        return result
