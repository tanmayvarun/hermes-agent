"""ContextActivation — associative, cheap, high-recall cue → memory activation.

Slice 1B: session-persistent workspace; activation is non-authoritative.
Does not commit bindings, desired_effects, or Goal identity.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from plugin.agent.brain.turn_representation import TurnRepresentation
from plugin.agent.brain.workspace import BrainWorkspace
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

# Cheap lexical arms only — cues, not semantic commitments / desired effects.
_ACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(send|message|text|ping|dm)\b", re.I), "send_message"),
    (re.compile(r"\b(forward|fwd)\b", re.I), "forward_message"),
    (re.compile(r"\b(call|ring|dial)\b", re.I), "call"),
    (re.compile(r"\b(open|launch)\b", re.I), "open"),
    (re.compile(r"\b(find|search|look\s+up)\b", re.I), "search"),
    (re.compile(r"\b(book|schedule|reserve)\b", re.I), "book"),
    (re.compile(r"\b(clean|cleanup|tidy)\b", re.I), "cleanup"),
    (re.compile(r"\b(continue|resume)\b", re.I), "continue"),
]

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
    "Continue",
    "Clean",
    "Downloads",
    "Like",
    "Last",
    "Time",
    "Work",
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
    project_topic_cues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lexical_cues": list(self.lexical_cues),
            "semantic_cues": list(self.semantic_cues),
            "action_cues": list(self.action_cues),
            "channel_cues": list(self.channel_cues),
            "context_cues": list(self.context_cues),
            "person_mentions": list(self.person_mentions),
            "project_topic_cues": list(self.project_topic_cues),
        }


def _structured_retrieve_capable(memory: Any) -> bool:
    """True when memory supports MemoryRetriever-style structured lookup."""
    return all(
        hasattr(memory, name)
        for name in ("find_entities_by_name", "get_entity", "get_aggregate")
    )


def _protocol_retrieve_capable(memory: Any) -> bool:
    return callable(getattr(memory, "retrieve", None))


def build_activation_signature(
    raw_turn: str,
    *,
    working_context: Optional[dict[str, Any]] = None,
) -> ActivationSignature:
    text = str(raw_turn or "").strip()
    lower = text.lower()
    sig = ActivationSignature()
    wc = dict(working_context or {})

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
        # Heuristic: "continue X work" / project-ish → topic cue; else person arm.
        if "continue" in lower or "project" in lower or "work" in lower:
            if name not in sig.project_topic_cues:
                sig.project_topic_cues.append(name)
        else:
            if name not in sig.person_mentions:
                sig.person_mentions.append(name)
        if name not in sig.lexical_cues:
            sig.lexical_cues.append(name)

    # Downloads / filesystem cleanup cues (non-person)
    if re.search(r"\bdownloads?\b", lower):
        if "Downloads" not in sig.lexical_cues:
            sig.lexical_cues.append("Downloads")
        if "filesystem" not in sig.semantic_cues:
            sig.semantic_cues.append("filesystem")
        if "cleanup" not in sig.semantic_cues:
            sig.semantic_cues.append("cleanup")

    for ch in sig.channel_cues:
        if ch not in sig.lexical_cues:
            sig.lexical_cues.append(ch)

    if any(a in {"send_message", "forward_message"} for a in sig.action_cues):
        for s in ("messaging", "communication"):
            if s not in sig.semantic_cues:
                sig.semantic_cues.append(s)
    if sig.person_mentions and "person" not in sig.semantic_cues:
        sig.semantic_cues.append("person")
    if sig.project_topic_cues or "continue" in sig.action_cues:
        if "project" not in sig.semantic_cues:
            sig.semantic_cues.append("project")

    # L1 working-context cues (session-local)
    for key in (
        "task",
        "project",
        "recent_entity",
        "recent_entity_name",
        "recent_project",
        "recent_topic",
    ):
        val = wc.get(key)
        if val:
            cue = f"{key}:{val}"
            if cue not in sig.context_cues:
                sig.context_cues.append(cue)
            sval = str(val).strip()
            if sval and sval not in sig.lexical_cues:
                sig.lexical_cues.append(sval)

    for name in list(wc.get("recent_entity_names") or []):
        n = str(name).strip()
        if not n:
            continue
        if n not in sig.lexical_cues:
            sig.lexical_cues.append(n)
        if n not in sig.person_mentions and n[:1].isupper():
            # Keep as lexical/L1; do not force person role — just a cue.
            if n not in sig.context_cues:
                sig.context_cues.append(f"l1_entity:{n}")

    for topic in list(wc.get("recent_topics") or []) + list(wc.get("recent_projects") or []):
        t = str(topic).strip()
        if t and t not in sig.project_topic_cues:
            sig.project_topic_cues.append(t)
        if t and t not in sig.lexical_cues:
            sig.lexical_cues.append(t)

    return sig


def _provisional_from_signature(
    raw_turn: str, sig: ActivationSignature
) -> TurnRepresentation:
    unresolved: list[dict[str, Any]] = []
    for mention in sig.person_mentions:
        unresolved.append(
            {
                "surface_form": mention,
                "role": "unknown",  # semantic roles belong to interpretation
                "candidate_types": ["person"],
                "entity_id": "UNKNOWN",
            }
        )
    for topic in sig.project_topic_cues:
        unresolved.append(
            {
                "surface_form": topic,
                "role": "unknown",
                "candidate_types": ["project", "topic"],
                "entity_id": "UNKNOWN",
            }
        )
    entity_types: list[str] = []
    if sig.person_mentions:
        entity_types.append("person")
    if sig.project_topic_cues:
        entity_types.append("project")
    return TurnRepresentation(
        raw_turn=raw_turn,
        detected_mentions=list(sig.person_mentions) + list(sig.project_topic_cues),
        possible_entity_types=entity_types,
        action_hints=list(sig.action_cues),
        channels=list(sig.channel_cues),
        project_topic_cues=list(sig.project_topic_cues),
        unresolved_references=unresolved,
        interpretation_status="provisional",
    )


def _evidence_row(ranked: Any, *, lifecycle: str, turn_id: str, cue: str = "") -> dict[str, Any]:
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
        "activation_cue": cue,
        "lifecycle": lifecycle,
        "activation_turn_id": turn_id,
        "source": "memory_retrieve",
    }


def _l1_evidence_from_working_context(
    wc: dict[str, Any], *, turn_id: str
) -> list[dict[str, Any]]:
    """Promote session working-context entities as high-salience L1 evidence."""
    rows: list[dict[str, Any]] = []
    eid = str(wc.get("recent_entity_id") or "").strip()
    ename = str(wc.get("recent_entity_name") or wc.get("recent_entity") or "").strip()
    if eid or ename:
        rows.append(
            {
                "ref": eid or f"l1:{ename}",
                "ref_kind": "entity",
                "final_score": 1.0,
                "canonical_name": ename,
                "aliases": [ename] if ename else [],
                "explanation": "l1_working_context",
                "feature_scores": {"l1_working_context": 1.0},
                "recall_sources": ["working_context"],
                "activation_cue": "l1",
                "lifecycle": "working",
                "activation_turn_id": turn_id,
                "source": "l1_working_context",
                "salience": "l1",
            }
        )
    for name in list(wc.get("recent_entity_names") or []):
        n = str(name).strip()
        if not n or (ename and n.lower() == ename.lower()):
            continue
        rows.append(
            {
                "ref": f"l1:{n}",
                "ref_kind": "entity",
                "final_score": 0.85,
                "canonical_name": n,
                "aliases": [n],
                "explanation": "l1_recent_entity_names",
                "feature_scores": {"l1_working_context": 0.85},
                "recall_sources": ["working_context"],
                "activation_cue": "l1",
                "lifecycle": "working",
                "activation_turn_id": turn_id,
                "source": "l1_working_context",
                "salience": "l1",
            }
        )
    for topic in list(wc.get("recent_projects") or []) + list(wc.get("recent_topics") or []):
        t = str(topic).strip()
        if not t:
            continue
        rows.append(
            {
                "ref": f"l1:project:{t}",
                "ref_kind": "project",
                "final_score": 0.9,
                "canonical_name": t,
                "aliases": [t],
                "explanation": "l1_project_topic",
                "feature_scores": {"l1_working_context": 0.9},
                "recall_sources": ["working_context"],
                "activation_cue": "l1",
                "lifecycle": "working",
                "activation_turn_id": turn_id,
                "source": "l1_working_context",
                "salience": "l1",
            }
        )
    return rows


def _merge_working_context(
    existing: dict[str, Any], incoming: Optional[dict[str, Any]]
) -> dict[str, Any]:
    """Preserve session L1 keys; overlay non-empty incoming fields."""
    out = dict(existing or {})
    for k, v in dict(incoming or {}).items():
        if v is None or v == "" or v == []:
            continue
        out[k] = v
    return out


def _update_l1_after_turn(ws: BrainWorkspace, sig: ActivationSignature) -> None:
    """Record cheap turn cues into lasting working context (not bindings)."""
    wc = dict(ws.working_context or {})
    recent_names = list(wc.get("recent_entity_names") or [])
    for name in sig.person_mentions:
        if name not in recent_names:
            recent_names.insert(0, name)
    wc["recent_entity_names"] = recent_names[:12]

    projects = list(wc.get("recent_projects") or [])
    for topic in sig.project_topic_cues:
        if topic not in projects:
            projects.insert(0, topic)
    if projects:
        wc["recent_projects"] = projects[:8]
        wc["recent_project"] = projects[0]

    turns = list(wc.get("recent_turns") or [])
    turns.insert(0, {"text": ws.turn, "ts": time.time()})
    wc["recent_turns"] = turns[:10]
    ws.working_context = wc


def activate_context(
    memory: Any,
    *,
    raw_turn: str,
    session_ref: str = "",
    working_context: Optional[dict[str, Any]] = None,
    workspace: Optional[BrainWorkspace] = None,
    limit_per_cue: int = 8,
) -> BrainWorkspace:
    """Associative activation into BrainWorkspace. Never commits bindings/Goal.

    Reuses ``workspace`` when provided (session-persistent). Does not clear
    ``bindings`` or write ``desired_effects``.
    """
    ws = workspace or BrainWorkspace()
    turn_id = f"t{int(time.time() * 1000)}"
    ws.turn = str(raw_turn or "")
    ws.session_ref = str(session_ref or ws.session_ref or "")
    ws.working_context = _merge_working_context(ws.working_context, working_context)
    ws.metadata["activation_turn_id"] = turn_id
    ws.metadata["activation_committed"] = False

    sig = build_activation_signature(ws.turn, working_context=ws.working_context)
    ws.activation_signature = sig.to_dict()
    provisional = _provisional_from_signature(ws.turn, sig)
    ws.provisional_interpretation = provisional
    ws.unresolved_references = list(provisional.unresolved_references)
    # Intentionally do NOT set ws.desired_effects — that is interpretation/brain.

    # Expire prior turn-local activation evidence; keep working/lifecycle evidence.
    kept = [
        e
        for e in (ws.retrieved_evidence or [])
        if str(e.get("lifecycle") or "") == "working"
    ]
    turn_local: list[dict[str, Any]] = []
    active_refs: list[str] = []

    # L1 first (session outranks global later when sorting).
    for row in _l1_evidence_from_working_context(ws.working_context, turn_id=turn_id):
        turn_local.append(row)
        ref = str(row.get("ref") or "")
        if ref and ref not in active_refs:
            active_refs.append(ref)

    if not _structured_retrieve_capable(memory) and not _protocol_retrieve_capable(memory):
        ws.retrieved_evidence = kept + turn_local
        ws.active_context_refs = active_refs
        ws.metadata["activation_status"] = "skip_no_retrieve"
        _update_l1_after_turn(ws, sig)
        _refresh_hypotheses(ws)
        return ws

    cues: Sequence[str] = []
    for c in list(sig.person_mentions) + list(sig.project_topic_cues) + list(sig.lexical_cues):
        if c and c not in cues:
            cues.append(c)
    # Also query L1 preferred entity name for structured memory enrichment.
    l1_name = str(
        ws.working_context.get("recent_entity_name")
        or ws.working_context.get("recent_entity")
        or ""
    ).strip()
    if l1_name and l1_name not in cues:
        cues = [l1_name, *cues]

    if not cues and not turn_local:
        ws.retrieved_evidence = kept
        ws.active_context_refs = [
            str(e.get("ref") or "") for e in kept if e.get("ref")
        ]
        ws.metadata["activation_status"] = "no_cues"
        _update_l1_after_turn(ws, sig)
        _refresh_hypotheses(ws)
        return ws

    channel = sig.channel_cues[0] if sig.channel_cues else ""
    seen = {str(e.get("ref") or "") for e in turn_local if e.get("ref")}

    try:
        if _structured_retrieve_capable(memory):
            from plugin.agent.memory.retriever import MemoryRetriever

            retriever = MemoryRetriever(memory)
            for cue in cues:
                purpose = (
                    "entity_resolution"
                    if cue in sig.person_mentions or cue == l1_name
                    else "factual_recall"
                )
                packet = retriever.retrieve(
                    MemoryQuery(
                        purpose=purpose,
                        text=cue,
                        current_context={
                            "channel": channel,
                            "user_entity_id": "user:local",
                            "activation": True,
                            "working_context": dict(ws.working_context),
                        },
                        limit=limit_per_cue,
                    )
                )
                for ranked in packet.ranked:
                    ref = str(getattr(ranked, "ref", "") or "")
                    if not ref or ref in seen:
                        continue
                    seen.add(ref)
                    row = _evidence_row(
                        ranked, lifecycle="activation", turn_id=turn_id, cue=cue
                    )
                    # Boost when matches L1 preferred entity.
                    if l1_name and l1_name.lower() in (
                        str(row.get("canonical_name") or "").lower(),
                        *[a.lower() for a in (row.get("aliases") or []) if isinstance(a, str)],
                    ):
                        row["final_score"] = float(row["final_score"]) + 0.5
                        row["salience"] = "l1_boosted"
                        row["feature_scores"] = {
                            **dict(row.get("feature_scores") or {}),
                            "l1_boost": 1.0,
                        }
                    turn_local.append(row)
                    active_refs.append(ref)
        else:
            # Protocol-only MemorySystem.retrieve → flat evidence list.
            for cue in cues:
                results = memory.retrieve(
                    cue,
                    context={
                        "purpose": "entity_resolution",
                        "channel": channel,
                        "activation": True,
                    },
                    limit=limit_per_cue,
                )
                for ev in results or []:
                    ref = str(getattr(ev, "memory_id", None) or getattr(ev, "subject", "") or "")
                    if not ref or ref in seen:
                        continue
                    seen.add(ref)
                    turn_local.append(
                        {
                            "ref": ref,
                            "ref_kind": str(getattr(ev, "kind", "") or "memory"),
                            "final_score": float(getattr(ev, "confidence", 0.0) or 0.0),
                            "canonical_name": str(getattr(ev, "subject", "") or ""),
                            "aliases": [],
                            "explanation": "protocol_retrieve",
                            "feature_scores": {},
                            "recall_sources": ["memory.retrieve"],
                            "activation_cue": cue,
                            "lifecycle": "activation",
                            "activation_turn_id": turn_id,
                            "source": "memory_protocol",
                        }
                    )
                    active_refs.append(ref)

        # L1-boosted / L1 rows first.
        turn_local.sort(
            key=lambda r: (
                0 if r.get("salience") in {"l1", "l1_boosted"} else 1,
                -float(r.get("final_score") or 0.0),
            )
        )
        ws.retrieved_evidence = kept + turn_local
        ws.active_context_refs = active_refs
        ws.metadata["activation_status"] = "ok"
        ws.metadata["evidence_count"] = len(ws.retrieved_evidence)
    except Exception as exc:
        logger.debug("context activation retrieve failed: %s", exc, exc_info=True)
        ws.retrieved_evidence = kept + turn_local
        ws.active_context_refs = active_refs
        ws.metadata["activation_status"] = "error"
        ws.metadata["activation_error"] = str(exc)

    _update_l1_after_turn(ws, sig)
    _refresh_hypotheses(ws)
    return ws


def _refresh_hypotheses(ws: BrainWorkspace) -> None:
    """Non-authoritative ranking hints for interpretation — not bindings."""
    hyps: list[dict[str, Any]] = []
    for e in ws.retrieved_evidence[:8]:
        hyps.append(
            {
                "entity_id": e.get("ref"),
                "canonical_name": e.get("canonical_name"),
                "score": e.get("final_score"),
                "salience": e.get("salience") or "l3",
                "source": e.get("source"),
            }
        )
    ws.hypotheses = hyps
    if ws.provisional_interpretation is not None:
        ws.provisional_interpretation.metadata["recipient_hypotheses"] = list(hyps)
        ws.provisional_interpretation.metadata["working_context"] = dict(
            ws.working_context or {}
        )


def consultation_context_from_workspace(ws: Optional[BrainWorkspace]) -> dict[str, Any]:
    """Projection of BrainWorkspace for interpret / consultants (Slice 1 adapter)."""
    if ws is None:
        return {}
    top = list(ws.retrieved_evidence or [])[:8]
    return {
        "entity_names": [
            str(e.get("canonical_name") or "")
            for e in top
            if e.get("canonical_name")
        ],
        "top_evidence": [
            {
                "ref": e.get("ref"),
                "canonical_name": e.get("canonical_name"),
                "score": e.get("final_score"),
                "salience": e.get("salience"),
                "source": e.get("source"),
                "lifecycle": e.get("lifecycle"),
            }
            for e in top
        ],
        "working_context": dict(ws.working_context or {}),
        "unresolved_references": list(ws.unresolved_references or []),
        "action_hints": list(
            (ws.provisional_interpretation.action_hints if ws.provisional_interpretation else [])
            or (ws.activation_signature or {}).get("action_cues")
            or []
        ),
        "channel_hints": list(
            (ws.provisional_interpretation.channels if ws.provisional_interpretation else [])
            or (ws.activation_signature or {}).get("channel_cues")
            or []
        ),
        "hypotheses": list(ws.hypotheses or []),
        "activation_signature": dict(ws.activation_signature or {}),
    }
