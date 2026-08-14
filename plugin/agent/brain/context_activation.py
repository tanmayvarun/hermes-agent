"""ContextActivation — associative, cheap, high-recall cue → memory activation.

Runs before semantic commitment. Does not resolve identity or mutate Goal.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from plugin.agent.brain.turn_representation import TurnRepresentation
from plugin.agent.brain.workspace import BrainWorkspace
from plugin.agent.memory.local_store import LocalMemorySystem
from plugin.agent.memory.retriever import MemoryRetriever
from plugin.agent.memory.types import MemoryQuery

logger = logging.getLogger(__name__)

_CHANNEL_CUES = {
    "whatsapp": "whatsapp",
    "wa": "whatsapp",
    "email": "email",
    "gmail": "email",
    "imessage": "imessage",
    "sms": "sms",
    "slack": "slack",
    "telegram": "telegram",
}

_ACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(send|message|text|ping|dm)\b", re.I), "send_message"),
    (re.compile(r"\b(forward|fwd)\b", re.I), "forward_message"),
    (re.compile(r"\b(call|ring|dial)\b", re.I), "call"),
    (re.compile(r"\b(open|launch)\b", re.I), "open"),
    (re.compile(r"\b(find|search|look\s+up)\b", re.I), "search"),
    (re.compile(r"\b(book|schedule|reserve)\b", re.I), "book"),
]

# Capitalized token sequences that look like person/project names (naive Day-0).
_PROPER_NAME = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b"
)
_STOP_MENTIONS = {
    "WhatsApp",
    "Email",
    "Gmail",
    "Slack",
    "Telegram",
    "IMessage",
    "Sms",
    "Send",
    "Forward",
    "Find",
    "Open",
    "The",
    "A",
    "An",
    "To",
    "On",
    "In",
    "For",
    "With",
    "From",
    "Hi",
    "Hello",
}


@dataclass
class ActivationSignature:
    """Cue bundle for associative activation — not a commitment."""

    lexical_cues: list[str] = field(default_factory=list)
    semantic_cues: list[str] = field(default_factory=list)
    action_cues: list[str] = field(default_factory=list)
    channel_cues: list[str] = field(default_factory=list)
    context_cues: list[str] = field(default_factory=list)
    person_mentions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lexical_cues": list(self.lexical_cues),
            "semantic_cues": list(self.semantic_cues),
            "action_cues": list(self.action_cues),
            "channel_cues": list(self.channel_cues),
            "context_cues": list(self.context_cues),
            "person_mentions": list(self.person_mentions),
        }


def build_activation_signature(
    raw_turn: str,
    *,
    working_context: Optional[dict[str, Any]] = None,
) -> ActivationSignature:
    text = str(raw_turn or "").strip()
    lower = text.lower()
    sig = ActivationSignature()

    for pat, hint in _ACTION_PATTERNS:
        if pat.search(text):
            if hint not in sig.action_cues:
                sig.action_cues.append(hint)

    for cue, channel in _CHANNEL_CUES.items():
        if re.search(rf"\b{re.escape(cue)}\b", lower):
            if channel not in sig.channel_cues:
                sig.channel_cues.append(channel)

    for m in _PROPER_NAME.finditer(text):
        name = m.group(1).strip()
        if name in _STOP_MENTIONS:
            continue
        if name not in sig.person_mentions:
            sig.person_mentions.append(name)
        if name not in sig.lexical_cues:
            sig.lexical_cues.append(name)

    for ch in sig.channel_cues:
        if ch not in sig.lexical_cues:
            sig.lexical_cues.append(ch)

    if sig.action_cues and any("send" in a or "forward" in a for a in sig.action_cues):
        sig.semantic_cues.extend(["messaging", "person", "communication"])
    if sig.person_mentions:
        if "person" not in sig.semantic_cues:
            sig.semantic_cues.append("person")

    wc = working_context or {}
    for key in ("task", "project", "recent_entity"):
        val = wc.get(key)
        if val:
            sig.context_cues.append(f"{key}:{val}")

    return sig


def _provisional_from_signature(
    raw_turn: str, sig: ActivationSignature
) -> TurnRepresentation:
    unresolved: list[dict[str, Any]] = []
    for mention in sig.person_mentions:
        unresolved.append(
            {
                "surface_form": mention,
                "role": "recipient" if sig.action_cues else "referent",
                "entity_id": "UNKNOWN",
            }
        )
    entity_types: list[str] = []
    if sig.person_mentions:
        entity_types.append("person")
    return TurnRepresentation(
        raw_turn=raw_turn,
        detected_mentions=list(sig.person_mentions),
        possible_entity_types=entity_types,
        action_hints=list(sig.action_cues),
        channels=list(sig.channel_cues),
        unresolved_references=unresolved,
        interpretation_status="provisional",
    )


def _evidence_row(ranked: Any) -> dict[str, Any]:
    payload = dict(getattr(ranked, "payload", None) or {})
    return {
        "ref": getattr(ranked, "ref", ""),
        "ref_kind": getattr(ranked, "ref_kind", "entity"),
        "final_score": float(getattr(ranked, "final_score", 0.0) or 0.0),
        "canonical_name": payload.get("canonical_name") or "",
        "aliases": list(payload.get("aliases") or []),
        "explanation": getattr(ranked, "explanation", "") or "",
        "feature_scores": dict(getattr(ranked, "feature_scores", None) or {}),
        "recall_sources": list(getattr(ranked, "recall_sources", None) or []),
    }


def activate_context(
    memory: Any,
    *,
    raw_turn: str,
    session_ref: str = "",
    working_context: Optional[dict[str, Any]] = None,
    workspace: Optional[BrainWorkspace] = None,
    limit_per_cue: int = 8,
) -> BrainWorkspace:
    """Associative activation into BrainWorkspace. Never commits bindings/Goal."""
    ws = workspace or BrainWorkspace()
    ws.turn = str(raw_turn or "")
    ws.session_ref = str(session_ref or ws.session_ref or "")
    ws.working_context = dict(working_context or ws.working_context or {})

    sig = build_activation_signature(ws.turn, working_context=ws.working_context)
    ws.activation_signature = sig.to_dict()
    provisional = _provisional_from_signature(ws.turn, sig)
    ws.provisional_interpretation = provisional
    ws.unresolved_references = list(provisional.unresolved_references)
    ws.desired_effects = list(sig.action_cues)

    # Clear prior activation evidence for this turn (do not clear committed bindings —
    # Slice 1 has none from activation).
    ws.retrieved_evidence = []
    ws.active_context_refs = []
    ws.bindings = []  # activation must not invent bindings
    ws.metadata["activation_committed"] = False

    if not isinstance(memory, LocalMemorySystem):
        ws.metadata["activation_status"] = "skip_memory_not_local"
        return ws

    if not sig.lexical_cues and not sig.person_mentions:
        ws.metadata["activation_status"] = "no_cues"
        return ws

    channel = sig.channel_cues[0] if sig.channel_cues else ""
    retriever = MemoryRetriever(memory)
    seen: set[str] = set()
    cues: Sequence[str] = list(sig.person_mentions) or list(sig.lexical_cues)

    try:
        for cue in cues:
            packet = retriever.retrieve(
                MemoryQuery(
                    purpose="entity_resolution",
                    text=cue,
                    current_context={
                        "channel": channel,
                        "user_entity_id": "user:local",
                        "activation": True,
                    },
                    limit=limit_per_cue,
                )
            )
            for ranked in packet.ranked:
                ref = str(getattr(ranked, "ref", "") or "")
                if not ref or ref in seen:
                    continue
                seen.add(ref)
                row = _evidence_row(ranked)
                row["activation_cue"] = cue
                ws.retrieved_evidence.append(row)
                ws.active_context_refs.append(ref)
        ws.metadata["activation_status"] = "ok"
        ws.metadata["evidence_count"] = len(ws.retrieved_evidence)
    except Exception as exc:
        logger.debug("context activation retrieve failed: %s", exc, exc_info=True)
        ws.metadata["activation_status"] = "error"
        ws.metadata["activation_error"] = str(exc)

    return ws
