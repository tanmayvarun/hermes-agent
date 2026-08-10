"""Overloaded revert / rollback capability (cross-task).

Graph nomenclature: backtrack ≡ revert ≡ rollback.

    analyze(effect_trace LIFO + typed blocking chrome) → RevertPlan
      → approve → execute allowlisted motors

Escape-class chrome (selection, filter chip, menu, picker) shares one motor:
``press_escape``. Legacy realization names normalize to it. Host overlays tag
``filter_chip`` observations; core never matches chip label string sets.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from plugin.agent.capabilities.base import CapabilityOutcome, TransientChrome
from plugin.agent.capabilities.branch_fitness import (
    blocking_chrome_from_document,
    compute_branch_fitness,
    selection_chrome_present,
    selection_count_from_document,
)
from plugin.agent.capabilities.dismiss_transient import (
    MACOS_DISMISS,
    DismissRuntime,
    MacDismissRuntime,
    dismiss_chord_for,
    dismiss_transient,
)

logger = logging.getLogger(__name__)

EFFECT_TRACE_CAP = 8

# Canonical Escape motor (+ legacy aliases accepted then normalized).
PRESS_ESCAPE = "press_escape"
_ESCAPE_ALIASES = frozenset(
    {
        PRESS_ESCAPE,
        "dismiss_transient",
        "clear_selection_escape",
        "dismiss_transient_chrome",
        "leave_picker_escape",
        "clear_search_filter",
    }
)

ALLOWLISTED_REALIZATIONS = frozenset({PRESS_ESCAPE}) | _ESCAPE_ALIASES

CONTRACTED_REALIZATIONS = frozenset(
    {
        "delete_committed_message",
        "remove_copied_file",
        "undo_edit",
    }
)

KNOWN_REALIZATIONS = ALLOWLISTED_REALIZATIONS | CONTRACTED_REALIZATIONS

HIGH_RISK_REALIZATIONS = frozenset(
    {
        "delete_committed_message",
        "remove_copied_file",
    }
)

# Coarse effect classes on effect_trace (hints only; undo_hint prefers).
EFFECT_CLASSES = frozenset(
    {
        "selection_chrome",
        "transient_chrome",
        "picker_open",
        "blocking_filter",
        "message_sent",
        "file_copied",
        "file_edited",
        "unknown",
    }
)

_CONTENT_KINDS = frozenset(
    {
        "message",
        "message_bubble",
        "link",
        "content",
        "media",
        "attachment",
        "image",
        "photo",
    }
)


def normalize_realization(name: str) -> str:
    """Map legacy Escape aliases to the canonical press_escape motor."""
    n = str(name or "").strip()
    if n in _ESCAPE_ALIASES:
        return PRESS_ESCAPE
    return n


@dataclass
class RevertStep:
    realization: str
    why: str = ""
    expected_after: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "")}


@dataclass
class RevertPlan:
    """Structured undo plan — must be approved before motors run."""

    goal_of_revert: str = ""
    steps: List[RevertStep] = field(default_factory=list)
    do_not_touch: List[str] = field(default_factory=list)
    risk: str = "low"
    evidence: List[str] = field(default_factory=list)
    approved: bool = False
    approval_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_of_revert": self.goal_of_revert,
            "steps": [s.to_dict() for s in self.steps],
            "do_not_touch": list(self.do_not_touch),
            "risk": self.risk,
            "evidence": list(self.evidence),
            "approved": bool(self.approved),
            "approval_reason": self.approval_reason,
        }


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def _objects(document: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    out: List[Dict[str, Any]] = []
    for obj in document.get("objects") or []:
        if isinstance(obj, dict):
            out.append(obj)
    return out


def active_filter_chip_label(document: Optional[Dict[str, Any]]) -> str:
    """Label of a typed filter_chip blocker, if any (observation only)."""
    for b in blocking_chrome_from_document(document):
        if b.get("type") == "filter_chip":
            return str(b.get("text") or "").strip()
    return ""


# Back-compat name for tests that still import active_search_filter.
active_search_filter = active_filter_chip_label


def search_filter_mismatch_error(
    document: Optional[Dict[str, Any]],
    *,
    goal_referents: Optional[Sequence[str]] = None,
    goal_needs_link_or_message: bool = True,
) -> Dict[str, Any]:
    """Deprecated shim → :func:`compute_branch_fitness` (filter_chip typed)."""
    _ = goal_needs_link_or_message
    from plugin.agent.capabilities.branch_fitness import needed_evidence_kinds_for_goal

    kinds = needed_evidence_kinds_for_goal(goal_kind="whatsapp_forward_message")
    fit = compute_branch_fitness(
        document,
        needed_kinds=kinds,
        goal_referents=goal_referents,
    )
    label = active_filter_chip_label(document)
    return {
        "consistent": bool(fit.get("admissible")),
        "applicable": bool(label) or bool(fit.get("blockers")),
        "matched": bool(fit.get("admissible")),
        "filter": label,
        "effect_class": "blocking_filter" if not fit.get("admissible") else "",
        "verdict": fit.get("verdict"),
        "reasons": list(fit.get("reasons") or []),
        "branch_fitness": fit,
    }


def _goal_tokens(
    goal_referents: Optional[Sequence[str]] = None,
    *,
    semantic_target: str = "",
    document: Optional[Dict[str, Any]] = None,
) -> List[str]:
    tokens: List[str] = []
    for item in goal_referents or []:
        t = _norm(item)
        if t and t not in tokens:
            tokens.append(t)
    st = _norm(semantic_target)
    if st and st not in tokens and st not in {"forward", "select", "message"}:
        tokens.append(st)
    for obj in _objects(document):
        if not obj.get("matches_goal"):
            continue
        kind = _norm(obj.get("kind"))
        text = _norm(obj.get("text") or obj.get("label"))
        if not text:
            continue
        if kind in _CONTENT_KINDS or "http" in text:
            if text not in tokens:
                tokens.append(text[:80])
    return tokens


def _text_matches_goal(text: str, tokens: Sequence[str]) -> bool:
    hay = _norm(text)
    if not hay or not tokens:
        return False
    for tok in tokens:
        if not tok:
            continue
        if tok in hay or hay in tok:
            return True
        # Loose token overlap for URLs / titles.
        parts = [p for p in re.split(r"[^\w]+", tok) if len(p) >= 4]
        if parts and any(p in hay for p in parts):
            return True
    return False


# Content-object probes (reveal/select): kind-ok is not enough when the goal
# carries content referents. Shared predicate — no host/string hardcoding.
_CONTENT_PROBE_KINDS = frozenset(
    {
        "message",
        "message_bubble",
        "message_link_preview",
        "link",
        "attachment",
        "media",
        "image",
        "video",
        "audio",
        "document",
        "outgoing_message",
        "incoming_message",
    }
)


def content_target_fits_referents(
    *,
    target_label: str = "",
    object_blob: str = "",
    goal_referents: Optional[Sequence[str]] = None,
) -> bool:
    """Candidate-recall only — NOT authoritative targeting.

    Loose token overlap may propose candidates. Authoritative act targeting
    must go through RoleBinding / IdentityResolver.
    """
    tokens = [str(t).strip() for t in (goal_referents or []) if str(t).strip()]
    if not tokens:
        return True
    blob = f"{target_label} {object_blob}".strip()
    return _text_matches_goal(blob, tokens)


def pick_unique_referent_content(
    document: Optional[Dict[str, Any]],
    goal_referents: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Candidate recall: unique content object overlapping referents, if any.

    Must not be used as sole authority for ACT — bind via RoleBinding.
    """
    tokens = [str(t).strip() for t in (goal_referents or []) if str(t).strip()]
    if not tokens:
        return None
    doc = document if isinstance(document, dict) else {}
    hits: List[Dict[str, Any]] = []
    for obj in _objects(doc):
        kind = _norm(obj.get("kind"))
        text = str(obj.get("text") or obj.get("label") or "")
        blob = f"{text} {obj.get('id') or ''}"
        is_content = kind in _CONTENT_PROBE_KINDS or "http" in _norm(text)
        if not is_content and not obj.get("matches_goal"):
            continue
        if obj.get("matches_goal") or _text_matches_goal(blob, tokens):
            hits.append(obj)
    if len(hits) == 1:
        return hits[0]
    # Prefer URL-shaped when several match.
    url_hits = [o for o in hits if "http" in _norm(o.get("text") or o.get("label"))]
    if len(url_hits) == 1:
        return url_hits[0]
    return None


def selection_consistency_error(
    document: Optional[Dict[str, Any]],
    *,
    goal_referents: Optional[Sequence[str]] = None,
    semantic_target: str = "",
    selected_label: str = "",
) -> Dict[str, Any]:
    """Detect goal-inconsistent selection chrome after an act.

    Domain-general: uses selection count + content labels vs goal tokens.
    Task strings appear only in evidence.
    """
    doc = document if isinstance(document, dict) else {}
    count = selection_count_from_document(doc)
    chrome = selection_chrome_present(doc)
    tokens = _goal_tokens(
        goal_referents, semantic_target=semantic_target, document=doc
    )
    objects = _objects(doc)

    content_objs = [
        o
        for o in objects
        if _norm(o.get("kind")) in _CONTENT_KINDS
        or "http" in _norm(o.get("text") or o.get("label"))
    ]
    goal_content = [
        o
        for o in content_objs
        if o.get("matches_goal")
        or _text_matches_goal(str(o.get("text") or o.get("label") or ""), tokens)
    ]
    non_goal_content = [
        o
        for o in content_objs
        if o not in goal_content
        and not o.get("matches_goal")
        and not _text_matches_goal(str(o.get("text") or o.get("label") or ""), tokens)
    ]

    selected_ok = True
    if selected_label and tokens:
        selected_ok = _text_matches_goal(selected_label, tokens)

    inconsistent = False
    reasons: List[str] = []
    if count is not None and count >= 2 and non_goal_content:
        inconsistent = True
        reasons.append(f"multi_select_count={count}_with_non_goal_content")
    if chrome and selected_label and tokens and not selected_ok:
        inconsistent = True
        reasons.append("selected_label_mismatches_goal")
    if count is not None and count >= 2 and tokens and not goal_content:
        inconsistent = True
        reasons.append("multi_select_without_goal_content")
    # Explicit selected/checked patient that does not match goal tokens.
    selected_objs = [
        o
        for o in content_objs
        if o.get("selected") or o.get("is_selected") or o.get("checked")
    ]
    if chrome and tokens and selected_objs:
        if not any(
            o.get("matches_goal")
            or _text_matches_goal(
                str(o.get("text") or o.get("label") or ""), tokens
            )
            for o in selected_objs
        ):
            inconsistent = True
            reasons.append("selected_patient_mismatches_goal")
    # Single-select chrome with only non-goal content visible as patient candidates.
    if (
        chrome
        and tokens
        and count == 1
        and non_goal_content
        and not goal_content
        and not selected_objs
    ):
        inconsistent = True
        reasons.append("selection_chrome_without_goal_content")

    if not chrome and count is None:
        return {
            "consistent": True,
            "applicable": False,
            "selection_count": None,
            "verdict": "no selection chrome to check",
            "reasons": [],
            "goal_tokens": tokens[:6],
        }

    if inconsistent:
        non_goal_preview = [
            str(o.get("text") or o.get("label") or "")[:60] for o in non_goal_content[:3]
        ]
        return {
            "consistent": False,
            "applicable": True,
            "matched": False,
            "selection_count": count,
            "verdict": (
                f"selection inconsistent with goal: {', '.join(reasons)}; "
                f"non_goal={non_goal_preview!r}"
            ),
            "reasons": reasons,
            "non_goal_preview": non_goal_preview,
            "goal_tokens": tokens[:6],
            "selection_chrome": True,
        }

    return {
        "consistent": True,
        "applicable": True,
        "matched": True,
        "selection_count": count,
        "verdict": (
            f"selection consistent (count={count}, goal_content={len(goal_content)})"
        ),
        "reasons": [],
        "goal_tokens": tokens[:6],
        "selection_chrome": chrome,
    }


def append_effect_trace(
    execution_state: Any,
    entry: Dict[str, Any],
    *,
    cap: int = EFFECT_TRACE_CAP,
) -> None:
    """Append one forward-leg step onto execution_state.effect_trace."""
    if execution_state is None or not isinstance(entry, dict) or not entry:
        return
    try:
        trace = list(getattr(execution_state, "effect_trace", None) or [])
        trace.append(dict(entry))
        if len(trace) > cap:
            del trace[0 : len(trace) - cap]
        execution_state.effect_trace = trace
    except Exception:
        logger.debug("append_effect_trace failed", exc_info=True)


def classify_effect(
    *,
    capability: str = "",
    target: str = "",
    intention: Optional[Dict[str, Any]] = None,
    document: Optional[Dict[str, Any]] = None,
    selection_consistency: Optional[Dict[str, Any]] = None,
) -> str:
    """Map a forward act (+ world) to a coarse effect class for analyze."""
    fam = _norm(capability)
    tgt = _norm(target)
    intent = intention if isinstance(intention, dict) else {}
    controls = [_norm(c) for c in (intent.get("likely_controls") or []) if _norm(c)]
    if fam == "commit_irreversible" and (
        tgt in {"send", "send message"} or any(c == "send" for c in controls)
    ):
        return "message_sent"
    if fam == "commit_irreversible" and "trash" in tgt:
        return "file_copied"
    if fam in {"select_content", "reveal_actions", "invoke_affordance"}:
        if isinstance(selection_consistency, dict) and selection_consistency.get(
            "consistent"
        ) is False:
            return "selection_chrome"
        if selection_chrome_present(document):
            return "selection_chrome"
    surface = _norm((document or {}).get("surface") if isinstance(document, dict) else "")
    blockers = blocking_chrome_from_document(document)
    if any(b.get("type") == "filter_chip" for b in blockers):
        return "blocking_filter"
    if surface in {"context_menu", "action_menu", "dialog"}:
        return "transient_chrome"
    if surface in {"forward_picker", "destination_picker"}:
        return "picker_open"
    if fam in {"type", "type_query", "compose_search_query"} and "edit" in " ".join(
        controls
    ):
        return "file_edited"
    return "unknown"


def undo_hint_for(
    *,
    effect_class: str = "",
    capability: str = "",
    document: Optional[Dict[str, Any]] = None,
) -> str:
    """Invertible motor hint for the effect_trace undo stack."""
    ec = _norm(effect_class) or classify_effect(
        capability=capability, document=document
    )
    if ec in {
        "selection_chrome",
        "transient_chrome",
        "picker_open",
        "blocking_filter",
        "wrong_search_filter",
    }:
        return PRESS_ESCAPE
    if ec == "message_sent":
        return "delete_committed_message"
    if ec == "file_copied":
        return "remove_copied_file"
    if ec == "file_edited":
        return "undo_edit"
    # Reversible UI acts default to Escape when chrome may have opened.
    fam = _norm(capability)
    if fam in {
        "select_content",
        "reveal_actions",
        "compose_search_query",
        "open_entity",
        "dismiss_transient",
    }:
        return PRESS_ESCAPE
    return ""


def record_act_on_effect_trace(
    execution_state: Any,
    *,
    capability: str,
    target: str = "",
    geometry: Optional[Sequence[float]] = None,
    intention: Optional[Dict[str, Any]] = None,
) -> None:
    intent = intention if isinstance(intention, dict) else {}
    effect_class = classify_effect(
        capability=capability, target=target, intention=intention
    )
    pre_surface = str(intent.get("surface") or "")
    entry: Dict[str, Any] = {
        "capability": str(capability or ""),
        "target": str(target or ""),
        "effect_class": effect_class,
        "undo_hint": undo_hint_for(
            effect_class=effect_class, capability=capability
        ),
        "pre_surface": pre_surface,
        "risk": (
            "high"
            if effect_class in {"message_sent", "file_copied"}
            else "low"
        ),
    }
    if isinstance(geometry, (list, tuple)) and len(geometry) >= 2:
        try:
            entry["geometry"] = [float(geometry[0]), float(geometry[1])]
        except (TypeError, ValueError):
            pass
    if intent:
        entry["intention"] = {
            k: intent.get(k)
            for k in ("surface", "likely_controls", "semantic_target", "action_family")
            if intent.get(k) not in (None, "", [])
        }
    append_effect_trace(execution_state, entry)


def update_effect_trace_after_look(
    execution_state: Any,
    *,
    prediction_error: Optional[Dict[str, Any]] = None,
    selection_consistency: Optional[Dict[str, Any]] = None,
    document: Optional[Dict[str, Any]] = None,
) -> None:
    """Attach post-act look results to the latest forward-leg entry."""
    if execution_state is None:
        return
    try:
        trace = list(getattr(execution_state, "effect_trace", None) or [])
        if not trace:
            return
        last = dict(trace[-1])
        if isinstance(prediction_error, dict) and prediction_error:
            last["prediction_error"] = {
                "matched": prediction_error.get("matched"),
                "predicted_surface": prediction_error.get("predicted_surface"),
                "observed_surface": prediction_error.get("observed_surface"),
                "verdict": str(prediction_error.get("verdict") or "")[:160],
            }
        if isinstance(selection_consistency, dict) and selection_consistency:
            last["selection_consistency"] = {
                "consistent": selection_consistency.get("consistent"),
                "selection_count": selection_consistency.get("selection_count"),
                "verdict": str(selection_consistency.get("verdict") or "")[:160],
            }
        if isinstance(document, dict):
            last["world_after"] = {
                "surface": str(document.get("surface") or "")[:40],
                "open_conversation": str(document.get("open_conversation") or "")[:80],
                "selection_count": selection_count_from_document(document),
            }
            last["post_surface"] = str(document.get("surface") or "")[:40]
            last["effect_class"] = classify_effect(
                capability=str(last.get("capability") or ""),
                target=str(last.get("target") or ""),
                intention=last.get("intention")
                if isinstance(last.get("intention"), dict)
                else None,
                document=document,
                selection_consistency=selection_consistency
                if isinstance(selection_consistency, dict)
                else None,
            )
            last["undo_hint"] = undo_hint_for(
                effect_class=str(last.get("effect_class") or ""),
                capability=str(last.get("capability") or ""),
                document=document,
            )
        trace[-1] = last
        execution_state.effect_trace = trace
    except Exception:
        logger.debug("update_effect_trace_after_look failed", exc_info=True)


def _step_for_motor(realization: str, *, why: str = "", expected_after: str = "") -> RevertStep:
    motor = normalize_realization(realization)
    if motor == PRESS_ESCAPE:
        return RevertStep(
            realization=PRESS_ESCAPE,
            why=why or "clear blocking chrome via Escape",
            expected_after=expected_after or "blocking chrome cleared",
        )
    return RevertStep(
        realization=motor,
        why=why,
        expected_after=expected_after,
    )


def _steps_from_effect_class(effect_class: str, *, why: str = "") -> List[RevertStep]:
    """Map a forward effect class to revert realizations (hints → motors)."""
    ec = _norm(effect_class)
    if ec in {
        "selection_chrome",
        "transient_chrome",
        "picker_open",
        "blocking_filter",
        "wrong_search_filter",
    }:
        expected = {
            "selection_chrome": "no selection chrome",
            "blocking_filter": "no filter chip",
            "wrong_search_filter": "no filter chip",
            "transient_chrome": "task surface without overlay",
            "picker_open": "conversation without picker",
        }.get(ec, "blocking chrome cleared")
        return [_step_for_motor(PRESS_ESCAPE, why=why or f"undo {ec}", expected_after=expected)]
    if ec == "message_sent":
        return [
            RevertStep(
                realization="delete_committed_message",
                why=why or "undo sent message via Delete",
                expected_after="sent message removed",
            )
        ]
    if ec == "file_copied":
        return [
            RevertStep(
                realization="remove_copied_file",
                why=why or "remove the copy created by the forward leg",
                expected_after="copied file gone",
            )
        ]
    if ec == "file_edited":
        return [
            RevertStep(
                realization="undo_edit",
                why=why or "undo the last edit",
                expected_after="edit reverted",
            )
        ]
    return []


def _steps_from_undo_hint(hint: str, *, why: str = "") -> List[RevertStep]:
    motor = normalize_realization(hint)
    if not motor:
        return []
    if motor == PRESS_ESCAPE:
        return [_step_for_motor(PRESS_ESCAPE, why=why or "undo_hint=press_escape")]
    if motor in KNOWN_REALIZATIONS:
        return [RevertStep(realization=motor, why=why or f"undo_hint={motor}")]
    return []


def _steps_from_blockers(blockers: Sequence[Dict[str, Any]]) -> List[RevertStep]:
    for b in blockers:
        if not isinstance(b, dict):
            continue
        if b.get("clearable") == "escape" or b.get("type") in {
            "filter_chip",
            "selection_chrome",
            "transient_overlay",
            "picker",
        }:
            why = f"clear {b.get('type')}"
            if b.get("text"):
                why += f" {b.get('text')!r}"
            expected = (
                "no filter chip"
                if b.get("type") == "filter_chip"
                else "no selection chrome"
                if b.get("type") == "selection_chrome"
                else "blocking chrome cleared"
            )
            return [_step_for_motor(PRESS_ESCAPE, why=why, expected_after=expected)]
    return []


def analyze_revert_plan(
    *,
    document: Optional[Dict[str, Any]] = None,
    effect_trace: Optional[Sequence[Dict[str, Any]]] = None,
    selection_consistency: Optional[Dict[str, Any]] = None,
    goal_referents: Optional[Sequence[str]] = None,
    semantic_target: str = "",
    user_intent: str = "",
    needed_kinds: Optional[Sequence[str]] = None,
    branch_fitness: Optional[Dict[str, Any]] = None,
) -> RevertPlan:
    """Build RevertPlan: LIFO undo stack first, then typed blocking chrome."""
    doc = document if isinstance(document, dict) else {}
    sel = selection_consistency
    if not isinstance(sel, dict) or not sel:
        sel = selection_consistency_error(
            doc,
            goal_referents=goal_referents,
            semantic_target=semantic_target,
        )

    evidence: List[str] = []
    if user_intent:
        evidence.append(f"user_intent={str(user_intent)[:80]}")
    if isinstance(sel, dict):
        evidence.append(f"selection_consistent={sel.get('consistent')}")
        if sel.get("selection_count") is not None:
            evidence.append(f"selection_count={sel.get('selection_count')}")
        for r in sel.get("reasons") or []:
            evidence.append(str(r))

    open_chat = str(doc.get("open_conversation") or "").strip()
    do_not_touch = []
    if open_chat:
        do_not_touch.append(f"open_conversation {open_chat}")

    steps: List[RevertStep] = []

    # 1) Trace-first: LIFO undo_hint / effect_class.
    for entry in reversed(list(effect_trace or [])[-4:]):
        if not isinstance(entry, dict):
            continue
        hint = str(entry.get("undo_hint") or "").strip()
        if hint:
            proposed = _steps_from_undo_hint(
                hint,
                why=f"undo_hint LIFO cap={entry.get('capability')}",
            )
            if proposed:
                steps.extend(proposed)
                evidence.append(f"undo_hint={hint}")
                break
        sc = (
            entry.get("selection_consistency")
            if isinstance(entry.get("selection_consistency"), dict)
            else {}
        )
        if sc.get("consistent") is False:
            steps.extend(
                _steps_from_effect_class(
                    "selection_chrome",
                    why="effect_trace reports inconsistent selection",
                )
            )
            evidence.append("effect_trace_selection_inconsistent")
            break
        ec = str(entry.get("effect_class") or "").strip()
        if not ec or ec == "unknown":
            ec = classify_effect(
                capability=str(entry.get("capability") or ""),
                target=str(entry.get("target") or ""),
                intention=entry.get("intention")
                if isinstance(entry.get("intention"), dict)
                else None,
                document=doc,
            )
        proposed = _steps_from_effect_class(
            ec,
            why=f"undo forward effect_class={ec} cap={entry.get('capability')}",
        )
        if proposed:
            steps.extend(proposed)
            evidence.append(f"effect_class={ec}")
            break

    # 2) Cold start / stale trace: only when branch fitness is inadmissible.
    if not steps:
        fit = branch_fitness if isinstance(branch_fitness, dict) else None
        if fit is None:
            fit = compute_branch_fitness(
                doc,
                needed_kinds=needed_kinds,
                goal_referents=goal_referents,
                selection_consistency=sel if isinstance(sel, dict) else None,
            )
        if fit.get("admissible") is False:
            for r in fit.get("reasons") or []:
                evidence.append(str(r))
            blockers = list(fit.get("blockers") or []) or blocking_chrome_from_document(doc)
            steps.extend(_steps_from_blockers(blockers))
            if steps:
                evidence.append("blocking_chrome")

    # 3) Selection inconsistency without explicit blocker typing.
    if (
        not steps
        and isinstance(sel, dict)
        and sel.get("consistent") is False
        and selection_chrome_present(doc)
    ):
        steps.extend(
            _steps_from_effect_class(
                "selection_chrome",
                why=str(sel.get("verdict") or "goal-inconsistent selection"),
            )
        )

    # Normalize Escape aliases on the plan.
    for s in steps:
        s.realization = normalize_realization(s.realization)

    contracted = [s.realization for s in steps if s.realization in CONTRACTED_REALIZATIONS]
    high = [s.realization for s in steps if s.realization in HIGH_RISK_REALIZATIONS]
    if high or contracted:
        risk = "high"
    elif steps and all(
        normalize_realization(s.realization) == PRESS_ESCAPE
        or s.realization in ALLOWLISTED_REALIZATIONS
        for s in steps
    ):
        risk = "low"
    else:
        risk = "medium"

    if steps and normalize_realization(steps[0].realization) == PRESS_ESCAPE:
        goal = "backtrack: clear blocking chrome so the goal branch is admissible"
    elif steps and steps[0].realization == "delete_committed_message":
        goal = "undo a sent message by deleting it"
    elif steps and steps[0].realization == "remove_copied_file":
        goal = "undo a file copy by removing the copy"
    elif steps and steps[0].realization == "undo_edit":
        goal = "undo the last file/text edit"
    else:
        goal = "backtrack/revert the last mistaken forward-leg effect"

    return RevertPlan(
        goal_of_revert=goal,
        steps=steps,
        do_not_touch=do_not_touch,
        risk=risk,
        evidence=evidence,
    )


def approve_revert_plan(
    plan: RevertPlan,
    *,
    force: bool = False,
    auto: bool = True,
) -> RevertPlan:
    """Executive/brain gate: accept low-risk allowlisted plans automatically.

    High-risk undos (delete sent message, remove copied file) never auto-approve
    — they need force / explicit executive acceptance because the mechanism is
    ``commit_irreversible``.
    """
    for s in plan.steps:
        s.realization = normalize_realization(s.realization)
    if force:
        plan.approved = True
        plan.approval_reason = "forced"
        return plan
    if not plan.steps:
        plan.approved = False
        plan.approval_reason = "empty_plan"
        return plan
    contracted = [s.realization for s in plan.steps if s.realization in CONTRACTED_REALIZATIONS]
    if contracted:
        plan.approved = False
        plan.approval_reason = f"contracted_realizations:{','.join(contracted)}"
        return plan
    unknown = [
        s.realization
        for s in plan.steps
        if normalize_realization(s.realization) not in KNOWN_REALIZATIONS
        and s.realization not in KNOWN_REALIZATIONS
    ]
    if unknown:
        plan.approved = False
        plan.approval_reason = f"unknown_realizations:{','.join(unknown)}"
        return plan
    if any(s.realization in HIGH_RISK_REALIZATIONS for s in plan.steps) or plan.risk == "high":
        plan.approved = False
        plan.approval_reason = "high_risk_needs_explicit_approval"
        return plan
    if plan.risk not in {"low", "medium"}:
        plan.approved = False
        plan.approval_reason = f"risk={plan.risk}"
        return plan
    if auto and plan.risk == "low":
        plan.approved = True
        plan.approval_reason = "auto_low_risk_allowlisted"
        return plan
    if auto and plan.risk == "medium" and len(plan.steps) == 1:
        plan.approved = True
        plan.approval_reason = "auto_single_step_medium"
        return plan
    plan.approved = False
    plan.approval_reason = "needs_explicit_approval"
    return plan


def _postcondition_holds(document: Optional[Dict[str, Any]], expected_after: str) -> bool:
    exp = _norm(expected_after)
    if not exp:
        return True
    if "no selection chrome" in exp:
        return not selection_chrome_present(document)
    if "no filter chip" in exp or "without media filter" in exp:
        return not any(
            b.get("type") == "filter_chip" for b in blocking_chrome_from_document(document)
        )
    return True


def execute_revert_plan(
    plan: RevertPlan,
    *,
    app: str,
    surface: str = "",
    overlay: Any = None,
    runtime: Optional[DismissRuntime] = None,
    document: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> CapabilityOutcome:
    """Run approved plan steps. Escape-class realizations share dismiss_transient."""
    if not plan.approved:
        return CapabilityOutcome(
            ok=False,
            capability="revert_effects",
            realization="rejected",
            message=f"revert plan not approved: {plan.approval_reason}",
            evidence={"plan": plan.to_dict()},
        )
    if not plan.steps:
        return CapabilityOutcome(
            ok=False,
            capability="revert_effects",
            realization="empty",
            message="revert plan has no steps",
            evidence={"plan": plan.to_dict()},
        )

    rt = runtime or MacDismissRuntime()
    chord = dismiss_chord_for(overlay) if overlay is not None else MACOS_DISMISS
    executed: List[Dict[str, Any]] = []

    for step in plan.steps:
        motor = normalize_realization(step.realization)
        if motor not in ALLOWLISTED_REALIZATIONS and step.realization not in ALLOWLISTED_REALIZATIONS:
            return CapabilityOutcome(
                ok=False,
                capability="revert_effects",
                realization=step.realization,
                message=f"realization not allowlisted: {step.realization}",
                evidence={"plan": plan.to_dict(), "executed": executed},
            )
        step.realization = motor
        if dry_run:
            executed.append(
                {
                    "realization": step.realization,
                    "dry_run": True,
                    "ok": True,
                    "message": f"dry_run:{step.realization}",
                }
            )
            continue
        chrome = TransientChrome(app=app or "WhatsApp", surface=surface or "selection")
        outcome = dismiss_transient(chrome, rt, chord=chord)
        executed.append(
            {
                "realization": step.realization,
                "ok": bool(outcome.ok),
                "message": outcome.message,
            }
        )
        if not outcome.ok:
            return CapabilityOutcome(
                ok=False,
                capability="revert_effects",
                realization=step.realization,
                message=outcome.message,
                evidence={"plan": plan.to_dict(), "executed": executed},
            )

    return CapabilityOutcome(
        ok=True,
        capability="revert_effects",
        realization=plan.steps[0].realization if len(plan.steps) == 1 else "multi_step",
        message=(
            f"revert executed steps={len(executed)} "
            f"realizations={[s.realization for s in plan.steps]}"
        ),
        evidence={
            "substrate": "effect_trace",
            "plan": plan.to_dict(),
            "executed": executed,
            "dry_run": dry_run,
            "postcondition_hint": plan.steps[-1].expected_after if plan.steps else "",
            "document_checked": _postcondition_holds(
                document, plan.steps[-1].expected_after if plan.steps else ""
            )
            if dry_run
            else None,
        },
    )


def revert_effects(
    *,
    app: str = "",
    surface: str = "",
    document: Optional[Dict[str, Any]] = None,
    effect_trace: Optional[Sequence[Dict[str, Any]]] = None,
    selection_consistency: Optional[Dict[str, Any]] = None,
    goal_referents: Optional[Sequence[str]] = None,
    semantic_target: str = "",
    user_intent: str = "",
    overlay: Any = None,
    runtime: Optional[DismissRuntime] = None,
    approve: bool = True,
    force_approve: bool = False,
    dry_run: bool = False,
    plan: Optional[RevertPlan] = None,
) -> CapabilityOutcome:
    """Analyze → approve → execute. Pass an existing plan to skip analyze."""
    built = plan or analyze_revert_plan(
        document=document,
        effect_trace=effect_trace,
        selection_consistency=selection_consistency,
        goal_referents=goal_referents,
        semantic_target=semantic_target,
        user_intent=user_intent,
    )
    if approve or force_approve:
        built = approve_revert_plan(built, force=force_approve, auto=approve)
    elif not built.approved:
        return CapabilityOutcome(
            ok=False,
            capability="revert_effects",
            realization="analyze_only",
            message="revert plan awaiting approval",
            evidence={"plan": built.to_dict()},
        )
    return execute_revert_plan(
        built,
        app=app,
        surface=surface,
        overlay=overlay,
        runtime=runtime,
        document=document,
        dry_run=dry_run,
    )


def goal_referents_from_context(
    *,
    execution_state: Any = None,
    goal: Any = None,
    extras: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Collect content goal tokens from goal / extras / last expectation."""
    tokens: List[str] = []
    extras = extras if isinstance(extras, dict) else {}
    for key in ("goal_referents", "link_query", "content_query"):
        val = extras.get(key)
        if isinstance(val, (list, tuple)):
            for item in val:
                t = str(item or "").strip()
                if t and t not in tokens:
                    tokens.append(t)
        else:
            t = str(val or "").strip()
            if t and t not in tokens:
                tokens.append(t)
    if goal is not None:
        for attr in ("link_query", "content_query", "query"):
            t = str(getattr(goal, attr, "") or "").strip()
            if t and t not in tokens:
                tokens.append(t)
    if execution_state is not None:
        exp = getattr(execution_state, "unified_last_expectation", None)
        if isinstance(exp, dict):
            st = str(exp.get("semantic_target") or "").strip()
            if st and st not in tokens:
                tokens.append(st)
        prior = getattr(execution_state, "last_selection_consistency", None)
        if isinstance(prior, dict):
            for t in prior.get("goal_tokens") or []:
                s = str(t or "").strip()
                if s and s not in tokens:
                    tokens.append(s)
    return tokens
