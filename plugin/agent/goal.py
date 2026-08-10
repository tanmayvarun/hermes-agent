"""Goal evaluation — thin; no planning."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Optional

from plugin.agent.action import Action
from plugin.agent.predicates import (
    CallStateIs,
    ContactResultVisible,
    ConversationOpen,
    NoUnexpectedDialog,
    SearchInputFocused,
    SearchQueryEquals,
)
from plugin.agent.reference.types import Reference
from plugin.worldmodel.model import WorldModel


@dataclass
class Goal:
    kind: str  # whatsapp_voice_call | whatsapp_forward_message | …
    contact: str = ""  # primary contact / search subject
    app: str = "WhatsApp"
    hangup_after: bool = False
    require_contact_in_call: bool = True
    # Voice: do not treat pre-existing ringing as success until agent start_call this session
    require_agent_initiated_call: bool = False
    reference: Optional[Reference] = None
    # Freeform / multi-party tasks
    prompt: str = ""
    target_contact: str = ""  # e.g. forward destination
    link_query: str = ""  # e.g. link/text to find
    # Message/file author/sender ("from Pallavi" / "I sent"). Distinct from
    # container (conversation_with). Empty → fall back to contact for "from X".
    originator: str = ""
    procedure_id: str = ""
    procedure_score: float = 0.0
    procedure_reasons: list[str] = field(default_factory=list)
    procedure: Optional[Any] = None

    def __post_init__(self) -> None:
        if self.reference is None and self.contact:
            from plugin.agent.reference import interpret_reference

            self.reference = interpret_reference(self.contact)
        if not str(self.originator or "").strip() and self.contact:
            # "from <contact>" default; "I sent …" sets originator="self" explicitly.
            self.originator = self.contact
        # Selection is eager so downstream consumers can treat the procedure as
        # an attached goal substrate rather than a late heuristic.
        try:
            self.ensure_procedure()
        except Exception:
            pass

    @staticmethod
    def _clean_prompt(text: str) -> str:
        return " ".join((text or "").strip().split())

    @staticmethod
    def _extract_name(patterns: tuple[str, ...], text: str) -> str:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            candidate = " ".join((match.group(1) or "").strip().split(" "))
            candidate = re.split(r"\b(?:on|in|and|for|to|from|with)\b", candidate, maxsplit=1, flags=re.IGNORECASE)[0]
            candidate = candidate.strip(" .,:;")
            if candidate:
                return candidate
        return ""

    @classmethod
    def infer_from_text(cls, text: str, *, app: str = "WhatsApp") -> "Goal":
        """Best-effort structured goal inference from a natural-language prompt."""
        prompt = cls._clean_prompt(text)
        lowered = prompt.lower()
        if not prompt:
            return cls(kind="unknown", app=app, prompt="")

        if "whatsapp" in lowered and any(keyword in lowered for keyword in ("forward", "share", "send", "find")):
            source = cls._extract_name(
                (
                    r"(?:sent\s+to|from|with)\s+([A-Z][\w .'-]{1,80}?)(?=\s+(?:on|in|and|for|to|from|with)\b|[.,;]|$)",
                    r"(?:chat|conversation)\s+(?:with\s+)?([A-Z][\w .'-]{1,80}?)(?=\s+(?:on|in|and|for|to|from|with)\b|[.,;]|$)",
                    r"(?:to|from)\s+([A-Z][\w .'-]{1,80}?)(?=\s+(?:on|in|and|for|to|from|with)\b|[.,;]|$)",
                ),
                prompt,
            )
            target = cls._extract_name(
                (
                    r"(?:forward|share|send)\s+(?:it\s+)?(?:to|with)\s+([A-Z][\w .'-]{1,80}?)(?=\s+(?:on|in|and|for|to|from|with)\b|[.,;]|$)",
                    r"(?:forward|share)\s+(?:to|with)\s+([A-Z][\w .'-]{1,80}?)(?=\s+(?:on|in|and|for|to|from|with)\b|[.,;]|$)",
                ),
                prompt,
            )
            link_query = cls._extract_name(
                (
                    r"(?:find|locate|search\s+for)\s+(?:the\s+)?(.+?)\s+link\b",
                    r"(?:find|locate|search\s+for)\s+(?:the\s+)?(.+?)\s+(?:message|note|post)\b",
                ),
                prompt,
            )
            # Directional originator: "I sent/shared" → self; "from X" → X.
            self_origin = bool(
                re.search(
                    r"\b(?:i|me|my)\s+(?:sent|shared|forwarded)\b"
                    r"|\b(?:the\s+)?(?:link|message|file|photo|document)\s+i\s+(?:sent|shared)\b",
                    lowered,
                )
            )
            originator = "self" if self_origin else (source or "")
            if "forward" in lowered or "share" in lowered or "send" in lowered:
                return cls(
                    kind="whatsapp_forward_message",
                    app=app,
                    prompt=prompt,
                    contact=source,
                    target_contact=target,
                    link_query=link_query,
                    originator=originator,
                )
            if "find" in lowered:
                return cls(
                    kind="whatsapp_read_message",
                    app=app,
                    prompt=prompt,
                    contact=source,
                    target_contact=target,
                    link_query=link_query,
                    originator=originator,
                )

        if "call" in lowered:
            cleaned = re.sub(r"\bon whatsapp\b", "", prompt, flags=re.I)
            cleaned = re.sub(r"^\s*(?:video\s+|voice\s+|audio\s+)?call\s+", "", cleaned, flags=re.I)
            cleaned = cleaned.strip(" .,:;")
            contact = cleaned or "Pallavi"
            return cls(kind="whatsapp_voice_call", app=app, prompt=prompt, contact=contact)

        return cls(kind="unknown", app=app, prompt=prompt)

    def needed_evidence_kinds(self) -> list[str]:
        """Coarse world evidence kinds this goal needs (not label strings)."""
        if self.kind in {"whatsapp_forward_message", "whatsapp_read_message"} or self.link_query:
            return [
                "message",
                "message_bubble",
                "link",
                "content",
                "chat_row",
                "search_result_row",
            ]
        if self.kind in {"whatsapp_voice_call", "whatsapp_video_call"}:
            return ["chat_row", "search_result_row", "conversation", "button"]
        return [
            "chat_row",
            "search_result_row",
            "conversation",
            "message",
            "message_bubble",
        ]

    @property
    def description(self) -> str:
        if self.prompt:
            return self.prompt
        if self.kind == "whatsapp_voice_call" and self.contact:
            return f"Call {self.contact} on {self.app}"
        if self.kind == "whatsapp_forward_message":
            return (
                f"Find {self.link_query or 'content'} from {self.contact} "
                f"and forward to {self.target_contact} on {self.app}"
            )
        return f"{self.kind} on {self.app}"

    def execution_context_block(self) -> str:
        """Short structured contract injected into generic turn drivers."""
        proc = self.ensure_procedure()
        hypotheses = self.intent_hypotheses()
        lines = [
            "Structured task contract:",
            f"- goal_kind: {self.kind}",
            f"- goal: {self.description}",
        ]
        if self.contact:
            lines.append(f"- contact: {self.contact}")
        if self.target_contact:
            lines.append(f"- target_contact: {self.target_contact}")
        if self.link_query:
            lines.append(f"- link_query: {self.link_query}")
        if self.procedure_id:
            lines.append(f"- procedure_id: {self.procedure_id}")
        if proc is not None:
            lines.append(f"- procedure_title: {proc.title}")
        if hypotheses:
            lines.append("- intent_hypotheses:")
            for idx, hypothesis in enumerate(hypotheses, start=1):
                lines.append(f"  {idx}. {hypothesis}")
        lines.append(
            "Treat this structured contract as the primary task; do not drift into unrelated WhatsApp call flows."
        )
        return "\n".join(lines)

    def ensure_reference(self) -> Reference:
        if self.reference is None:
            from plugin.agent.reference import interpret_reference

            self.reference = interpret_reference(self.contact or "")
        return self.reference

    def ensure_procedure(self):
        if self.procedure is not None:
            return self.procedure
        try:
            from plugin.agent.procedure import select_best_procedure

            selection = select_best_procedure(self)
        except Exception:
            selection = None
        if selection is None:
            return None
        self.procedure = selection.definition
        self.procedure_id = selection.definition.id
        self.procedure_score = float(selection.score or 0.0)
        self.procedure_reasons = list(selection.reasons or [])
        return self.procedure

    @staticmethod
    def _split_prompt_hints(text: str) -> list[str]:
        cleaned = " ".join((text or "").strip().split())
        if not cleaned:
            return []
        parts = [
            p.strip(" .;:-")
            for p in re.split(r"\b(?:then|and then|and|after that|afterward|next)\b|[;,]", cleaned, flags=re.I)
        ]
        out: list[str] = []
        seen = set()
        for part in parts:
            part = " ".join(part.split())
            if len(part) < 3:
                continue
            low = part.lower()
            if low in seen:
                continue
            seen.add(low)
            out.append(part)
        return out

    def intent_hypotheses(self) -> list[str]:
        """Ordered, prompt-derived subgoals used by the generic selector.

        The model should reason over these hypotheses before it commits to a
        specific actuator. This stays generic: the core sees intent structure,
        while overlays still own app-specific surface semantics.
        """
        out: list[str] = []
        seen = set()

        def add(value: str) -> None:
            text = " ".join((value or "").strip().split())
            if not text:
                return
            low = text.lower()
            if low in seen:
                return
            seen.add(low)
            out.append(text)

        proc = self.ensure_procedure()
        if proc is not None:
            try:
                for item in proc.stage_objectives(self):
                    add(item)
            except Exception:
                pass

        if self.kind == "whatsapp_forward_message":
            if self.link_query:
                add(f"find source content matching {self.link_query}")
            if self.contact:
                add(f"open source conversation {self.contact}")
            add("inspect source conversation timeline")
            add("identify the source message or link")
            if self.target_contact:
                add(f"forward to {self.target_contact}")
        elif self.kind == "whatsapp_voice_call":
            if self.contact:
                add(f"open conversation with {self.contact}")
            add("reach the call surface")
        else:
            if self.contact:
                add(self.contact)
            if self.target_contact:
                add(self.target_contact)
            if self.link_query:
                add(self.link_query)

        for hint in self._split_prompt_hints(self.prompt):
            add(hint)
        return out

    def family_key(self) -> str:
        """Coarse reusable family for related goals.

        Keeps call variants together (voice/video call) and groups message-style
        tasks together so the agent can reuse broad trajectory knowledge across
        near-neighbor goals without hardcoding app-specific cases at scoring time.
        """
        kind = (self.kind or "").strip().lower()
        if not kind:
            return "unknown"
        parts = [p for p in kind.split("_") if p]
        if not parts:
            return kind
        app = parts[0]
        if "call" in parts:
            return f"{app}_call"
        if "message" in parts:
            return f"{app}_message"
        if "search" in parts:
            return f"{app}_search"
        if "forward" in parts:
            return f"{app}_forward"
        return kind

    def signature_key(self) -> str:
        """Goal-specific signature used for trajectory memory bucketing."""
        parts = [
            self.family_key(),
            (self.contact or "").strip().lower(),
            (self.target_contact or "").strip().lower(),
            (self.link_query or "").strip().lower(),
        ]
        return "|".join(parts)

    def search_text(self, hypothesis_index: int = 0) -> str:
        ref = self.ensure_reference()
        hyps = ref.search_hypotheses or [ref.name or self.contact]
        if not hyps:
            return self.contact
        i = max(0, min(hypothesis_index, len(hyps) - 1))
        return hyps[i]


@dataclass
class GoalStatus:
    succeeded: bool = False
    impossible: bool = False
    reason: str = ""
    evidence: Optional[dict] = None


def evaluate_goal(goal: Goal, world: WorldModel) -> GoalStatus:
    from plugin.agent.apps.registry import get_overlay

    overlay = get_overlay(goal.app, world)
    return overlay.evaluate_goal(goal, world)


def expected_predicate_for(step: Action, contact: str = ""):
    """Map an Action to a WorldPredicate for post-execute verification."""
    act = step.action.lower()
    sem = (step.semantic_target or "").lower()
    text = step.text or contact
    if act == "click" and sem == "search":
        return SearchInputFocused()
    if act == "type":
        return SearchQueryEquals(text)
    if act == "click" and contact and contact.lower() in sem:
        return ConversationOpen(contact)
    if act == "click" and sem in {"call", "voice call", "audio call"}:
        return CallStateIs("ringing")
    if act == "click" and "end" in sem:
        return CallStateIs("idle")
    if act == "dismiss":
        return NoUnexpectedDialog()
    if act == "click" and text:
        return ContactResultVisible(text) if "call" not in sem else CallStateIs("ringing")
    return SearchInputFocused()
