"""World-model critic: propose/review residual updates to the carried document.

The multimodal perceptor does heavy sensor fusion and *proposes* a world
document. This module accepts or rejects structural deltas against the prior
accepted document, last runtime result, and a small navigation graph.

Structure first, judgement on appeal. Cheap deterministic rules settle the
ordinary frame -- a legal surface transition, an inventory that drifted by a row
-- at no cost. What they cannot account for is escalated to a model (see
``plugin.agent.critic_coherence``), because a hand-written table can tell that a
change is unexplained but not whether *this* change makes sense, which requires
knowing what the action meant. Without a judge the rules decide alone, which is
what every offline caller and eval relies on.

The residual applies to the object inventory as well as the scalar fields. It
originally did not, and the inventory is the part carrying the geometry the agent
clicks: a reading that replaced every visible row was waved through with the
reason "proposal provided soft content", which is precisely the delta capable of
sending a click somewhere that does not exist.

The critic owns two halves of the same judgement. ``critique_world_proposal``
settles *what is true* (the accepted document). ``note_topology_evidence`` and
``reconcile_frontier`` settle *what can be done about it* (the action topology):
an affordance the runtime measured as inert stops being offered, and controls a
confirmed reveal put on screen stop being described as latent. Without this the
frontier was rebuilt from scratch every frame with no memory of what had already
been proven not to work, so the perceptor kept being handed a dead control as a
live option and kept choosing it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

# Open-document titles that are really the focused search field's chrome
# (caret, placeholder, filter prompt) — never a conversation / entity referent.
# General UI: a search affordance echo is not "what is open".
_SEARCH_FIELD_ECHO = re.compile(
    # WA Mac AX/OCR: "Search", "Search|", "Q Search|", "• Search|", "· Search"
    r"^([•·▪●◦]\s*)?(q\s+)?search\|?$"
    r"|^([•·▪●◦]\s*)?search\s*(chats?|messages?|or\s+start)?.*"
    r"|^type\s+(a\s+)?search.*"
    r"|^cmd\s*\+\s*f.*"
    r"|^filter\s*(chats?|messages?)?$",
    re.IGNORECASE,
)


def is_search_field_echo(open_title: Any, *, search_query: Any = "") -> bool:
    """True when ``open_conversation`` is search-field chrome, not a referent."""
    raw = str(open_title or "").strip()
    if not raw:
        return False
    if _SEARCH_FIELD_ECHO.match(raw):
        return True
    low = raw.lower()
    # Strip common AX/OCR bullets before the glyph+Search checks.
    low_stripped = re.sub(r"^[•·▪●◦]+\s*", "", low).strip()
    if _SEARCH_FIELD_ECHO.match(low_stripped):
        return True
    # AX often prefixes the search glyph: "Q Search|", "Q Search chats and …"
    if (low.startswith("q ") or low_stripped.startswith("q ")) and "search" in low:
        return True
    # Typed query still in the search chrome: "Q Pallavi zarooratwala link||"
    if low.startswith("q ") and ("|" in low or low.count(" ") >= 2):
        return True
    # OCR of a focused search AXValue, live: "227 a Pallavi zarooratwala link"
    if re.match(r"^\d{1,4}\s+[a-z]\s+\S+", low):
        return True
    # Typed query echoed back as the "open" title (same tokens, not a chat name).
    sq = str(search_query or "").strip().lower()
    if sq:
        q_tokens = [t for t in re.findall(r"[a-z0-9]{3,}", sq)]
        if len(q_tokens) >= 2:
            hits = sum(1 for t in q_tokens if t in low)
            if hits >= max(2, len(q_tokens) - 1):
                return True
        sq_compact = re.sub(r"[^a-z0-9]+", "", sq)
        low_compact = re.sub(r"[^a-z0-9]+", "", low)
        if sq_compact and len(sq_compact) >= 6 and (
            sq_compact in low_compact or low_compact in sq_compact
        ):
            return True
    return False


def _open_referent_from_objects(objects: Sequence[Any]) -> str:
    """Best contact/header label from inventory when open title is unusable."""
    best = ""
    for obj in objects or []:
        if not isinstance(obj, dict):
            continue
        kind = str(obj.get("kind") or "").strip().lower()
        text = str(obj.get("text") or obj.get("label") or "").strip()
        if not text or is_search_field_echo(text):
            continue
        if kind in {"chat_header", "header", "conversation_header"}:
            return text.split("\n")[0].strip()[:80]
        if kind in {"chat_row", "contact", "entity"} and obj.get("matches_goal"):
            best = best or text.split("\n")[0].strip()[:80]
    return best

# Closed surface vocabulary (must stay aligned with unified_cognition).
CANONICAL_SURFACES: Set[str] = {
    "chat_list",
    "conversation",
    "search",
    "context_menu",
    "selection_mode",
    "forward_picker",
    "dialog",
    "blank",
}

# Parent / predecessor surfaces that may legally lead to a child.
# Missing edge ⇒ critic keeps the prior surface unless last action explains it.
SURFACE_PARENTS: Dict[str, Set[str]] = {
    "chat_list": {"blank", "conversation", "search", "dialog", "chat_list"},
    "search": {"chat_list", "conversation", "search", "blank"},
    "conversation": {
        "chat_list",
        "search",
        "conversation",
        "dialog",
        "forward_picker",
        "selection_mode",
        "context_menu",
    },
    "context_menu": {"conversation", "selection_mode"},
    # Multi-select chrome ("N Selected" + toolbar verbs) — not a context menu.
    "selection_mode": {"conversation", "context_menu", "selection_mode"},
    "forward_picker": {
        "context_menu",
        "conversation",
        "dialog",
        "forward_picker",
        "selection_mode",
    },
    "dialog": {
        "conversation",
        "chat_list",
        "search",
        "forward_picker",
        "context_menu",
        "selection_mode",
        "dialog",
    },
    "blank": set(CANONICAL_SURFACES),
}

# Actions that justify landing on a surface even without a parent edge.
ACTION_OPENS_SURFACE: Dict[str, Set[str]] = {
    "forward_picker": {
        "invoke_affordance",
        "forward_message",
        "reveal_actions",
        "resolve_entity",
        "open_entity",
        "type_query",
    },
    "context_menu": {"reveal_actions", "context_click"},
    "selection_mode": {"select_content", "reveal_actions", "invoke_affordance"},
    "search": {"type_query", "compose_search_query", "open_search", "open_entity"},
    "conversation": {"open_entity", "open_contact", "locate_content", "select_content"},
    "dialog": {"invoke_affordance", "commit_irreversible", "click"},
}

# Focused editable field role implied by surface when the model omits it.
SURFACE_FIELD_ROLE: Dict[str, str] = {
    "forward_picker": "destination_filter",
    "search": "sidebar_search",
    "chat_list": "sidebar_search",
    "conversation": "in_chat_or_composer",
    "context_menu": "none",
    "selection_mode": "none",
    "dialog": "dialog_field",
    "blank": "none",
}

# Surfaces where sidebar Cmd+F / source compose+type remaps are illegal.
NO_SIDEBAR_SEARCH_SURFACES: Set[str] = {
    "forward_picker",
    "context_menu",
    "selection_mode",
    "dialog",
}

SIDEBAR_SEARCH_ROLES: Set[str] = {"sidebar_search"}


# --- object inventory residual ------------------------------------------------
#
# The document's scalar fields (surface, open_conversation, field role) were the
# only ones held to the residual discipline; ``objects`` was accepted wholesale.
# That is backwards. The inventory carries the geometry the agent clicks, so a
# frame whose objects are entirely different from the last one is the delta that
# can actually do damage — and it was the one nothing examined.
#
# Between two consecutive micro-actions the visible inventory cannot turn over
# completely unless something made it: the surface changed, the viewport moved,
# or a filter was applied. A total replacement with none of those is far more
# likely a misread than a real screen.

# Actions that move the viewport without changing surface, so a largely new
# inventory on the same surface is exactly what they are for.
VIEWPORT_ACTIONS: Set[str] = {
    "scroll",
    "scroll_conversation",
    "scroll_to",
    "locate_content",
    "page_down",
    "page_up",
}

# Actions that re-filter what a surface lists, which legitimately replaces the
# inventory in place.
FILTER_ACTIONS: Set[str] = {"type_query", "compose_search_query", "clear_query", "type_text"}

# Fraction of the prior inventory that must vanish *and* of the new inventory
# that must be unfamiliar before a same-surface reading counts as a wholesale
# rewrite rather than ordinary drift. Deliberately high: the cost of examining a
# real change is a held-back frame, while the cost of waving through a fabricated
# one is the agent acting on furniture that is not there.
RADICAL_CHURN = 0.7

# A handful of objects is too small a sample for a ratio to mean anything: going
# from two rows to two different rows is 100% churn and says nothing.
MIN_INVENTORY_FOR_CHURN = 4


@dataclass
class ObjectDelta:
    """What changed between two object inventories."""

    persisted: List[str] = field(default_factory=list)
    appeared: List[str] = field(default_factory=list)
    disappeared: List[str] = field(default_factory=list)
    prior_count: int = 0
    proposed_count: int = 0

    @property
    def churn(self) -> float:
        """Fraction of the prior inventory that is no longer reported."""
        if not self.prior_count:
            return 0.0
        return len(self.disappeared) / float(self.prior_count)

    @property
    def replacement(self) -> float:
        """Fraction of the proposed inventory that was not there before."""
        if not self.proposed_count:
            return 0.0
        return len(self.appeared) / float(self.proposed_count)

    def summary(self) -> str:
        return (
            f"{len(self.persisted)} kept, {len(self.appeared)} new, "
            f"{len(self.disappeared)} gone (churn {self.churn:.2f})"
        )


def _object_texts(objects: Any) -> List[str]:
    out: List[str] = []
    for item in objects or []:
        if not isinstance(item, dict):
            continue
        text = _norm_label(item.get("text"))
        if text:
            out.append(text)
    return out


def diff_object_inventories(prior: Any, proposed: Any) -> ObjectDelta:
    """Compare two inventories by the text the user would read.

    Identity is the visible text rather than the model's ids, because the ids are
    regenerated every frame and carry no continuity — comparing them would report
    a total rewrite on every look.
    """
    prior_texts = _object_texts(prior)
    proposed_texts = _object_texts(proposed)
    prior_set, proposed_set = set(prior_texts), set(proposed_texts)
    return ObjectDelta(
        persisted=sorted(prior_set & proposed_set),
        appeared=sorted(proposed_set - prior_set),
        disappeared=sorted(prior_set - proposed_set),
        prior_count=len(prior_set),
        proposed_count=len(proposed_set),
    )


def inventory_rewrite_is_explained(
    delta: ObjectDelta,
    *,
    surface_changed: bool,
    last_action: str,
) -> tuple[bool, str]:
    """Whether a wholesale change of inventory has an account of itself.

    Returns explained=True for anything that is not a wholesale rewrite, so the
    ordinary frame costs nothing. Only the unexplained rewrite is held back for
    judgement.
    """
    if delta.prior_count < MIN_INVENTORY_FOR_CHURN:
        return True, "no prior inventory worth comparing"
    if delta.churn < RADICAL_CHURN or delta.replacement < RADICAL_CHURN:
        return True, f"ordinary drift: {delta.summary()}"
    if surface_changed:
        return True, "surface changed; a new inventory is expected"
    action = _norm_label(last_action)
    if any(token in action for token in VIEWPORT_ACTIONS):
        return True, f"{last_action!r} moves the viewport; new items are expected"
    if any(token in action for token in FILTER_ACTIONS):
        return True, f"{last_action!r} refilters the surface; a new list is expected"
    return False, (
        f"inventory rewritten on an unchanged surface with no action to explain it "
        f"({delta.summary()}, last={last_action or 'none'!r})"
    )


@dataclass
class CriticDecision:
    field: str
    verdict: str  # accept | reject | edit
    reason: str
    prior: Any = None
    proposed: Any = None
    accepted: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "verdict": self.verdict,
            "reason": self.reason,
            "prior": self.prior,
            "proposed": self.proposed,
            "accepted": self.accepted,
        }


@dataclass
class CriticVerdict:
    """Residual merge of a perceptor proposal into the accepted world document."""

    accepted_document: Dict[str, Any]
    decisions: List[CriticDecision] = field(default_factory=list)
    focused_field_role: str = "none"
    surface: str = ""
    forbid_sidebar_search_motor: bool = False
    forbid_source_compose_remap: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "surface": self.surface,
            "focused_field_role": self.focused_field_role,
            "forbid_sidebar_search_motor": self.forbid_sidebar_search_motor,
            "forbid_source_compose_remap": self.forbid_source_compose_remap,
            "decisions": [d.to_dict() for d in self.decisions],
            "accepted_document": self.accepted_document,
        }


def _norm_surface(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    if text in CANONICAL_SURFACES:
        return text
    # Mild aliases the model sometimes emits.
    aliases = {
        "chatlist": "chat_list",
        "list": "chat_list",
        "search_results": "search",
        "picker": "forward_picker",
        "forward": "forward_picker",
        "destination_picker": "forward_picker",
        "menu": "context_menu",
        "action_menu": "context_menu",
        "multi_select": "selection_mode",
        "multiselect": "selection_mode",
        "select_messages": "selection_mode",
        "selection": "selection_mode",
    }
    return aliases.get(text, text if text else "")


# Search-result chrome tokens (Links / Messages / All, etc.). Presence of these
# while a cloud patch claims conversation is high-quality contradictory evidence.
_SEARCH_RESULT_CHROME_TOKENS = frozenset(
    {
        "links",
        "messages",
        "all",
        "chats",
        "groups",
        "unread",
        "photos",
        "videos",
        "gifs",
        "documents",
        "stickers",
        "audio",
    }
)


def search_surface_evidence(
    proposal: Optional[Dict[str, Any]],
    *,
    prior: Optional[Dict[str, Any]] = None,
    observed_surface: str = "",
    prediction_error: Optional[Dict[str, Any]] = None,
) -> tuple[bool, str]:
    """Return whether direct observation contradicts a conversation surface claim.

    Prediction error is belief-changing evidence, not telemetry: when the last
    look already scored predicted=conversation / observed=search, a subsequent
    cloud patch proposing conversation must not become authoritative.
    """
    prop = proposal if isinstance(proposal, dict) else {}
    prior_doc = prior if isinstance(prior, dict) else {}
    obs = _norm_surface(observed_surface or prop.get("observed_surface"))
    if obs in {"search", "search_results"}:
        return True, f"observed_surface={obs}"

    pe = prediction_error if isinstance(prediction_error, dict) else {}
    pe_obs = _norm_surface(pe.get("observed_surface"))
    pe_pred = _norm_surface(pe.get("predicted_surface"))
    if pe.get("matched") is False and pe_obs in {"search", "search_results"}:
        return True, (
            f"prediction_error observed={pe_obs} "
            f"(predicted={pe_pred or 'conversation'})"
        )

    search_query = str(
        prop.get("search_query") or prior_doc.get("search_query") or ""
    ).strip()
    if search_query:
        # Active query with no conversation composer/header is search scope.
        has_conversation_chrome = False
        for item in prop.get("objects") or prior_doc.get("objects") or []:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip().lower()
            if kind in {"chat_header", "message_bubble", "composer", "input_field"}:
                text = str(item.get("text") or item.get("label") or "").strip()
                if kind == "chat_header" and text and not is_search_field_echo(text):
                    has_conversation_chrome = True
                    break
                if kind in {"message_bubble", "composer"}:
                    has_conversation_chrome = True
                    break
        if not has_conversation_chrome:
            return True, f"active search_query={search_query!r} without conversation chrome"

    chrome_hits: List[str] = []
    for item in prop.get("objects") or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        text = re.sub(
            r"^[\s•·]+", "", str(item.get("text") or item.get("label") or "")
        ).strip()
        token = text.split()[0].lower() if text else ""
        if kind == "filter_chip" or (
            kind in {"chip", "tab", "segment"} and token in _SEARCH_RESULT_CHROME_TOKENS
        ):
            chrome_hits.append(token or kind)
        elif token in _SEARCH_RESULT_CHROME_TOKENS and kind in {
            "",
            "static",
            "label",
            "text",
        }:
            chrome_hits.append(token)
    if chrome_hits:
        return True, f"search result chrome present ({', '.join(chrome_hits[:4])})"

    return False, ""


def _last_action_family(prior: Dict[str, Any], last_action: str = "") -> str:
    if last_action:
        return str(last_action or "").strip().lower()
    attempts = list(prior.get("attempts") or [])
    if not attempts:
        return ""
    last = attempts[-1]
    if isinstance(last, dict):
        return str(last.get("action") or "").strip().lower()
    return str(last or "").strip().lower()


def infer_field_role(surface: str, proposed: Optional[Dict[str, Any]] = None) -> str:
    if isinstance(proposed, dict):
        role = str(
            proposed.get("focused_field_role")
            or proposed.get("field_role")
            or ""
        ).strip().lower()
        if role:
            return role
    return SURFACE_FIELD_ROLE.get(surface, "none")


def _surface_transition_ok(
    prior_surface: str,
    proposed_surface: str,
    *,
    last_action: str,
) -> tuple[bool, str]:
    if not proposed_surface:
        return False, "empty proposed surface"
    if proposed_surface not in CANONICAL_SURFACES:
        return False, f"non-canonical surface {proposed_surface!r}"
    if not prior_surface or prior_surface == proposed_surface:
        return True, "same or initial surface"
    parents = SURFACE_PARENTS.get(proposed_surface, set())
    if prior_surface in parents:
        # A prior, not a law: while hunting inside a conversation, falling into
        # sidebar search is usually a misread rather than a real move. It is
        # app-and-task-specific knowledge, so it refuses rather than decides —
        # the surface judge in critic_coherence can overturn it when the action
        # really does explain the jump. Left here as remaining debt: this belongs
        # with the WhatsApp overlay, not in the general coherence layer.
        if (
            prior_surface == "conversation"
            and proposed_surface == "search"
            and last_action
            in {"locate_content", "select_content", "reveal_actions", "observe"}
        ):
            return False, (
                f"refuse conversation->search during {last_action!r}; "
                "sidebar search abandons the open-chat hunt"
            )
        return True, f"{prior_surface} is a legal parent of {proposed_surface}"
    openers = ACTION_OPENS_SURFACE.get(proposed_surface, set())
    if last_action and any(tok in last_action for tok in openers):
        # Typing on a picker/dialog must not "explain" a jump into sidebar search.
        if prior_surface in NO_SIDEBAR_SEARCH_SURFACES and proposed_surface in {
            "search",
            "chat_list",
        }:
            return False, (
                f"refuse {prior_surface!r}->{proposed_surface!r}: "
                f"sidebar search is not reachable from picker/dialog via {last_action!r}"
            )
        return True, f"last action {last_action!r} opens {proposed_surface}"
    # Jumping to blank / dialog is usually recovery chrome; allow with note.
    if proposed_surface in {"blank", "dialog"}:
        return True, f"recovery surface {proposed_surface}"
    return False, (
        f"illegal jump {prior_surface!r} -> {proposed_surface!r} "
        f"without justifying action (last={last_action!r})"
    )


def critique_world_proposal(
    prior: Optional[Dict[str, Any]],
    proposal: Dict[str, Any],
    *,
    last_action: str = "",
    observed_surface: str = "",
    prediction_error: Optional[Dict[str, Any]] = None,
    coherence_judge: Optional[Any] = None,
    surface_judge: Optional[Any] = None,
) -> CriticVerdict:
    """Merge ``proposal`` into ``prior`` with structural accept/reject reasons.

    ``coherence_judge`` is an optional callable consulted only when the
    deterministic rules find a change they cannot account for. It exists because
    the rules can detect that an inventory was rewritten without cause but cannot
    know whether *this* rewrite makes sense, which requires understanding what the
    action meant. Absent a judge the rules decide alone, which is the behaviour
    every offline caller and eval depends on.

    ``prediction_error`` (when present) is authoritative surface evidence: a
    high-quality observed contradiction must reject/downgrade a cloud patch that
    claims conversation while the screen remains search/search_results.
    """
    prior_doc = dict(prior or {})
    prop = dict(proposal or {})
    decisions: List[CriticDecision] = []

    prior_surface = _norm_surface(prior_doc.get("surface"))
    proposed_surface = _norm_surface(prop.get("surface") or observed_surface)
    action = _last_action_family(prior_doc, last_action)

    ok, reason = _surface_transition_ok(
        prior_surface, proposed_surface, last_action=action
    )
    # SURFACE_PARENTS is one application's topology typed out by hand, so its
    # refusals conflate "this cannot happen" with "nobody wrote this edge down".
    # Only the first is a real incoherence; the second discards a correct reading
    # and cannot generalise past the app it was written for. Route the refusal to
    # judgement and let the table keep only its cheap accepts. Vocabulary is not
    # appealable: a surface outside the enum has no field role, no revealed-surface
    # semantics and no phase mapping downstream, so it stays refused.
    if (
        not ok
        and surface_judge is not None
        and proposed_surface in CANONICAL_SURFACES
        and prior_surface
    ):
        try:
            ok, judged_reason = surface_judge(
                prior_surface=prior_surface,
                proposed_surface=proposed_surface,
                last_action=action,
                rule_reason=reason,
            )
            reason = judged_reason or reason
        except Exception:
            pass

    # Authority: direct search evidence beats a legal parent-edge accept of
    # conversation. Parent legality answers "could this jump happen?"; evidence
    # answers "did it?". Live 210526 accepted conversation while prediction_error
    # repeatedly reported observed=search.
    search_ev, search_why = search_surface_evidence(
        prop,
        prior=prior_doc,
        observed_surface=observed_surface,
        prediction_error=prediction_error,
    )
    if (
        ok
        and proposed_surface == "conversation"
        and search_ev
        and action
        not in {"open_entity", "open_contact", "locate_content", "select_content"}
    ):
        ok = False
        reason = (
            f"refuse conversation patch: contradictory search evidence ({search_why})"
        )
    elif (
        ok
        and proposed_surface == "conversation"
        and search_ev
        and action in {"open_entity", "open_contact", "locate_content", "select_content"}
        and _norm_surface(
            (prediction_error or {}).get("observed_surface")
            if isinstance(prediction_error, dict)
            else ""
        )
        in {"search", "search_results"}
        and (prediction_error or {}).get("matched") is False
    ):
        # Even a navigation opener fails when the post-act look still reads search.
        ok = False
        reason = (
            f"refuse conversation after {action}: post-act look still search "
            f"({search_why})"
        )

    if ok and proposed_surface:
        surface = proposed_surface
        decisions.append(
            CriticDecision(
                field="surface",
                verdict="accept",
                reason=reason,
                prior=prior_surface,
                proposed=proposed_surface,
                accepted=surface,
            )
        )
    else:
        # Prefer search when conversation was refused for search evidence.
        if (
            not ok
            and proposed_surface == "conversation"
            and search_ev
        ):
            surface = (
                prior_surface
                if prior_surface in {"search", "chat_list"}
                else "search"
            )
        else:
            surface = prior_surface or proposed_surface or "blank"
        decisions.append(
            CriticDecision(
                field="surface",
                verdict="reject" if prior_surface else "edit",
                reason=reason or "kept prior surface",
                prior=prior_surface,
                proposed=proposed_surface,
                accepted=surface,
            )
        )

    # Selection chrome ("N Selected" + toolbar) must not stay labeled context_menu.
    try:
        from plugin.agent.capabilities.branch_fitness import selection_chrome_present

        chrome_doc = {
            "objects": list(prop.get("objects") or prior_doc.get("objects") or []),
            "surface": surface,
        }
        if selection_chrome_present(chrome_doc) and surface in {
            "conversation",
            "context_menu",
            "action_menu",
            "",
        }:
            decisions.append(
                CriticDecision(
                    field="surface",
                    verdict="edit",
                    reason="selection chrome present — coerce to selection_mode",
                    prior=surface,
                    proposed=proposed_surface,
                    accepted="selection_mode",
                )
            )
            surface = "selection_mode"
    except Exception:
        pass

    # open_conversation: do not wipe a confirmed open without evidence.
    # Also refuse search-field chrome as an open referent (AX title latch).
    prior_open = str(prior_doc.get("open_conversation") or "").strip()
    prop_open = str(prop.get("open_conversation") or "").strip()
    search_query = str(
        prop.get("search_query") or prior_doc.get("search_query") or ""
    ).strip()
    if prior_open and is_search_field_echo(prior_open, search_query=search_query):
        prior_open = ""
    recovered = _open_referent_from_objects(prop.get("objects") or prior_doc.get("objects") or [])
    if prop_open and is_search_field_echo(prop_open, search_query=search_query):
        open_conversation = (
            prior_open
            if prior_open and not is_search_field_echo(prior_open, search_query=search_query)
            else recovered
        )
        decisions.append(
            CriticDecision(
                field="open_conversation",
                verdict="reject",
                reason=(
                    "proposal open_conversation is search-field chrome, not a "
                    "document referent; kept prior/header"
                ),
                prior=prior_open,
                proposed=prop_open,
                accepted=open_conversation,
            )
        )
    elif prop_open and surface == "search" and search_ev:
        # Conversation referent claim while search evidence won the surface.
        open_conversation = ""
        decisions.append(
            CriticDecision(
                field="open_conversation",
                verdict="reject",
                reason=(
                    "refuse open_conversation while search evidence keeps "
                    f"surface=search ({search_why})"
                ),
                prior=prior_open,
                proposed=prop_open,
                accepted=open_conversation,
            )
        )
    elif prop_open:
        open_conversation = prop_open
        decisions.append(
            CriticDecision(
                field="open_conversation",
                verdict="accept",
                reason="proposal named an open conversation",
                prior=prior_open,
                proposed=prop_open,
                accepted=open_conversation,
            )
        )
    elif prior_open and surface in {
        "conversation",
        "context_menu",
        "selection_mode",
        "forward_picker",
    }:
        open_conversation = prior_open
        decisions.append(
            CriticDecision(
                field="open_conversation",
                verdict="reject",
                reason=(
                    "proposal cleared open_conversation while still on a "
                    "conversation-descended surface; kept prior"
                ),
                prior=prior_open,
                proposed=prop_open,
                accepted=open_conversation,
            )
        )
    else:
        open_conversation = prop_open or prior_open or (
            recovered
            if surface
            in {"conversation", "context_menu", "selection_mode", "forward_picker"}
            else ""
        )
        decisions.append(
            CriticDecision(
                field="open_conversation",
                verdict="accept" if prop_open == prior_open else "edit",
                reason="merged open_conversation",
                prior=prior_open,
                proposed=prop_open,
                accepted=open_conversation,
            )
        )

    # Wishful open latch: conversation was refused for search evidence.
    if (
        surface == "search"
        and search_ev
        and proposed_surface == "conversation"
        and open_conversation
    ):
        decisions.append(
            CriticDecision(
                field="open_conversation",
                verdict="reject",
                reason=(
                    "clear open_conversation: surface kept as search under "
                    f"contradictory evidence ({search_why})"
                ),
                prior=prior_open,
                proposed=prop_open or open_conversation,
                accepted="",
            )
        )
        open_conversation = ""

    field_role = infer_field_role(surface, prop)
    # If the surface proposal was rejected, ignore the proposed field role —
    # it belongs to the discarded surface (e.g. sidebar_search on a hunt).
    if surface != proposed_surface:
        field_role = SURFACE_FIELD_ROLE.get(surface, "none")
        decisions.append(
            CriticDecision(
                field="focused_field_role",
                verdict="edit",
                reason="surface rejected; field role taken from accepted surface",
                proposed=str(prop.get("focused_field_role") or ""),
                accepted=field_role,
            )
        )
    # Structural override: picker/menu never imply sidebar search.
    elif surface in NO_SIDEBAR_SEARCH_SURFACES and field_role in SIDEBAR_SEARCH_ROLES:
        decisions.append(
            CriticDecision(
                field="focused_field_role",
                verdict="edit",
                reason=f"{surface} cannot host sidebar_search; coerced to destination_filter/none",
                prior=field_role,
                proposed=field_role,
                accepted=SURFACE_FIELD_ROLE.get(surface, "none"),
            )
        )
        field_role = SURFACE_FIELD_ROLE.get(surface, "none")
    else:
        decisions.append(
            CriticDecision(
                field="focused_field_role",
                verdict="accept",
                reason="field role from surface/proposal",
                proposed=str(prop.get("focused_field_role") or ""),
                accepted=field_role,
            )
        )

    accepted = dict(prop)
    # Carry forward prior keys the proposal omitted.
    for key, value in prior_doc.items():
        if key not in accepted or accepted.get(key) in (None, "", [], {}):
            accepted[key] = value
    accepted["surface"] = surface
    accepted["open_conversation"] = open_conversation
    accepted["focused_field_role"] = field_role

    # The object inventory is held to the same residual discipline as the scalar
    # fields. It used to be waved through with the other soft bags, which meant
    # the one delta carrying clickable geometry was the one nothing checked.
    if "objects" in prop and prop.get("objects") not in (None, "", [], {}):
        delta = diff_object_inventories(prior_doc.get("objects"), prop.get("objects"))
        explained, why = inventory_rewrite_is_explained(
            delta,
            surface_changed=surface != prior_surface,
            last_action=action,
        )
        if not explained and coherence_judge is not None:
            # Deterministic rules can tell that a rewrite is unaccounted for, but
            # not whether this particular one makes sense — that needs to know
            # what the action means. Ask, and let the answer overrule the rule.
            try:
                explained, judged_why = coherence_judge(
                    prior=prior_doc,
                    proposed=prop,
                    delta=delta,
                    surface=surface,
                    prior_surface=prior_surface,
                    last_action=action,
                )
                why = judged_why or why
            except Exception:
                pass
        if explained:
            accepted["objects"] = prop.get("objects")
            decisions.append(
                CriticDecision(
                    field="objects",
                    verdict="accept",
                    reason=why,
                    prior=delta.prior_count,
                    proposed=delta.proposed_count,
                    accepted="(set)",
                )
            )
        else:
            # Keep the carried inventory. x survives; this Δx has not earned the
            # right to replace it. The reading is not discarded — it reaches the
            # log through the narration, and the next frame gets another chance
            # with an action history that may explain it.
            accepted["objects"] = prior_doc.get("objects") or []
            decisions.append(
                CriticDecision(
                    field="objects",
                    verdict="reject",
                    reason=why,
                    prior=delta.prior_count,
                    proposed=delta.proposed_count,
                    accepted="(kept prior)",
                )
            )

    # Soft bags: prefer proposal when present.
    for key in ("progress", "attempts", "exhausted"):
        if key in prop and prop.get(key) not in (None, "", [], {}):
            accepted[key] = prop.get(key)
            decisions.append(
                CriticDecision(
                    field=key,
                    verdict="accept",
                    reason="proposal provided soft content",
                    accepted="(set)",
                )
            )

    # Beliefs are special: omission is a valid retraction, so an empty list
    # must clear any carried-forward belief inventory.
    if "beliefs" in prop:
        accepted["beliefs"] = prop.get("beliefs") or []
        decisions.append(
            CriticDecision(
                field="beliefs",
                verdict="accept",
                reason="belief retraction is explicit by omission/empty list",
                accepted="(set)" if accepted["beliefs"] else "[]",
            )
        )

    # Layer push/pop + object permanence (flagged). Overlay must not erase the
    # container beneath; stack ops replace flat surface-jump special cases.
    layer_decision = _accept_layers(
        prior_doc, accepted, last_action=action, surface=surface
    )
    if layer_decision is not None:
        decisions.append(layer_decision)
        try:
            from plugin.agent.scene_layers import (
                derive_flat,
                layered_perception_enabled,
                normalize_layers,
            )

            if layered_perception_enabled() and accepted.get("layers"):
                _top_surface, base_name = derive_flat(
                    normalize_layers(accepted["layers"])
                )
                if base_name and not str(accepted.get("open_conversation") or "").strip():
                    accepted["open_conversation"] = base_name
                    open_conversation = base_name
        except Exception:
            pass

    forbid_sidebar_motor = (
        surface in NO_SIDEBAR_SEARCH_SURFACES or field_role == "destination_filter"
    )

    return CriticVerdict(
        accepted_document=accepted,
        decisions=decisions,
        focused_field_role=field_role,
        surface=surface,
        forbid_sidebar_search_motor=forbid_sidebar_motor,
        forbid_source_compose_remap=forbid_sidebar_motor,
    )


def accepted_surface(execution_state: Any) -> str:
    doc = getattr(execution_state, "unified_world_document", None) or {}
    if isinstance(doc, dict):
        return _norm_surface(doc.get("surface"))
    return ""


def accepted_field_role(execution_state: Any) -> str:
    role = str(getattr(execution_state, "focused_field_role", "") or "").strip().lower()
    if role:
        return role
    doc = getattr(execution_state, "unified_world_document", None) or {}
    if isinstance(doc, dict):
        return infer_field_role(_norm_surface(doc.get("surface")), doc)
    return "none"


def sidebar_search_forbidden(execution_state: Any = None, *, surface: str = "", role: str = "") -> bool:
    surf = surface or (accepted_surface(execution_state) if execution_state is not None else "")
    field = role or (accepted_field_role(execution_state) if execution_state is not None else "")
    return surf in NO_SIDEBAR_SEARCH_SURFACES or field == "destination_filter"


# --- action topology ---------------------------------------------------------
#
# The document says what is true; the frontier says what can be done. Both are
# the critic's to settle, because the same measured outcome updates both: an
# ``open_entity`` that moved nothing is evidence about the world *and* proof
# that this particular control is not the one that opens that conversation.

# Effects that prove the action reached the app and the app did nothing. These
# are the ones that condemn an affordance. Effects where the action never landed
# (missing geometry, a failed actuator) say nothing about the control itself, so
# they must not condemn it.
_INERT_EFFECTS: Set[str] = {"no_transition"}

# Surfaces that only exist because something was revealed onto them.
_REVEALED_SURFACES: Set[str] = {"context_menu", "forward_picker", "dialog"}

MAX_DEAD_AFFORDANCES = 12


def _norm_label(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def affordance_key(surface: str, family: str, target: str) -> str:
    """Stable identity for 'this control, on this surface'."""
    return f"{_norm_surface(surface)}|{_norm_label(family)}|{_norm_label(target)}"


def note_topology_evidence(
    execution_state: Any,
    *,
    last_action_family: str,
    last_target: str,
    effect_kind: str,
    surface: str,
) -> Optional[Dict[str, str]]:
    """Record what the last action proved about the action topology.

    Called on the critic step, once the accepted document has settled what
    surface we are actually on. An action that reached the app and moved nothing
    condemns the affordance it used: offering it again as a live option is how
    the agent ends up re-clicking a control that has already been measured inert.
    Returns the record it added, or None when the outcome proves nothing.
    """
    family = _norm_label(last_action_family)
    target = _norm_label(last_target)
    if not family or _norm_label(effect_kind) not in _INERT_EFFECTS:
        return None
    record = {
        "key": affordance_key(surface, family, target),
        "surface": _norm_surface(surface),
        "family": family,
        "target": target,
        "reason": "measured inert: the app did not move when this was invoked",
    }
    dead = list(getattr(execution_state, "dead_affordances", None) or [])
    if any(item.get("key") == record["key"] for item in dead if isinstance(item, dict)):
        return None
    dead.append(record)
    if len(dead) > MAX_DEAD_AFFORDANCES:
        del dead[0 : len(dead) - MAX_DEAD_AFFORDANCES]
    try:
        execution_state.dead_affordances = dead
    except Exception:
        return None
    return record


def _iter_document_objects(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flat objects plus per-layer objects (action_menu items live on layers)."""
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for obj in list(document.get("objects") or []):
        if not isinstance(obj, dict):
            continue
        key = (
            str(obj.get("text") or obj.get("label") or "").strip().lower(),
            str(obj.get("point") or ""),
        )
        if key[0] and key not in seen:
            seen.add(key)
            out.append(obj)
    for layer in document.get("layers") or []:
        if not isinstance(layer, dict):
            continue
        for obj in layer.get("objects") or []:
            if not isinstance(obj, dict):
                continue
            key = (
                str(obj.get("text") or obj.get("label") or "").strip().lower(),
                str(obj.get("point") or ""),
            )
            if key[0] and key not in seen:
                seen.add(key)
                out.append(obj)
    return out


_MENU_KINDS = frozenset({"menu_item", "menuitem", "menu", "action", "affordance"})


def _grounded_from_objects(
    document: Dict[str, Any], *, prefer_menu: bool = False
) -> List[Any]:
    """The document's own objects, shaped as grounded reveal actions.

    After a confirmed reveal the perceptor reports the menu entries it can now
    see, each with the point it would click. That is exactly the grounding
    ``ground_revealed`` consumes, so the controls a probe exposed stop being
    described to the model as latent.
    """
    from types import SimpleNamespace

    from plugin.perception.coordinate_frame import (
        FrameGraph,
        resolve_frame_id_for_space,
    )

    graph = None
    raw_graph = document.get("frame_graph")
    if isinstance(raw_graph, FrameGraph):
        graph = raw_graph
    elif isinstance(raw_graph, dict):
        try:
            graph = FrameGraph.from_dict(raw_graph)
        except Exception:
            graph = None
    if graph is None:
        surface_meta = document.get("task_surface")
        if isinstance(surface_meta, dict) and surface_meta.get("frame_graph"):
            try:
                graph = FrameGraph.from_dict(surface_meta.get("frame_graph"))
            except Exception:
                graph = None

    out: List[Any] = []
    for obj in _iter_document_objects(document):
        label = str(obj.get("text") or obj.get("label") or "").strip()
        point = obj.get("point")
        if not label or not point:
            continue
        kind = str(obj.get("kind") or "").strip().lower()
        if prefer_menu and kind and kind not in _MENU_KINDS:
            # When promoting under a reveal handoff with flat surface still
            # conversation, only take explicit menu_item-like objects — not
            # every message bubble with a point.
            if not bool(obj.get("is_menu_item")):
                continue
        target: Dict[str, Any] = {"point": list(point)}
        if obj.get("id") is not None:
            target["entity_id"] = obj.get("id")
        space = str(obj.get("coordinate_space") or "").strip().lower()
        if space in {"screen", "image"}:
            target["coordinate_space"] = space
        geo = str(obj.get("geometry_source") or obj.get("source") or "").strip()
        if geo:
            target["geometry_source"] = geo[:40]
        owner = str(obj.get("owner_surface") or obj.get("surface") or "").strip()
        if owner:
            target["owner_surface"] = owner[:40]
        cid = str(
            obj.get("capture_id") or obj.get("grounding_capture_id") or ""
        ).strip()
        if cid:
            target["capture_id"] = cid[:80]
        # Document-level WHEN stamp when object row omitted it (same observe).
        # Frame IDs are space-specific — never copy a generic document.frame_id.
        if not target.get("capture_id"):
            doc_cid = str(document.get("capture_id") or "").strip()
            if doc_cid:
                target["capture_id"] = doc_cid[:80]
        if space in {"screen", "image"}:
            raw_fid = str(
                obj.get("frame_id") or obj.get("coordinate_frame_id") or ""
            ).strip()
            fid = resolve_frame_id_for_space(
                frame_id=raw_fid,
                coordinate_space=space,
                graph=graph,
            )
            if fid:
                target["frame_id"] = fid[:80]
        out.append(
            SimpleNamespace(
                label=label,
                is_grounded=True,
                target=target,
                confidence=0.9 if kind in _MENU_KINDS else 0.8,
            )
        )
    return out


def _reveal_handoff_active(execution_state: Any) -> bool:
    handoff = getattr(execution_state, "reveal_handoff", None) if execution_state else None
    return isinstance(handoff, dict) and bool(str(handoff.get("surface") or "").strip())


def _document_has_action_menu_layer(document: Dict[str, Any]) -> bool:
    for layer in document.get("layers") or []:
        if not isinstance(layer, dict):
            continue
        if str(layer.get("role") or "").strip().lower() in {"action_menu", "context_menu"}:
            return True
    return False


_MENU_VERB_LABELS = frozenset(
    {
        "forward",
        "forward message",
        "forward messages",
        "reply",
        "react",
        "star",
        "pin",
        "copy",
        "info",
        "delete",
        "select messages",
        "share",
    }
)


def _label_looks_like_menu_verb(label: str) -> bool:
    """True for context-menu verbs; false for 'Forwarded…' chat chrome."""
    text = str(label or "").strip().lower()
    text = re.sub(r"^[\s•·▪●◦\-–—]+", "", text).strip()
    if not text or text.startswith("forwarded"):
        return False
    return text in _MENU_VERB_LABELS


def enrich_document_menu_verbs_from_ocr(
    document: Optional[Dict[str, Any]],
    ocr_lines: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Under reveal handoff, fold OCR menu verbs into document objects.

    Does **not** invent into ``affordance_set`` — only enriches the accepted
    world document so ``reconcile_frontier`` / post-accept promote can ground
    Forward (etc.) from measured OCR geometry (live 125715 empty-frontier class).
    """
    doc = dict(document) if isinstance(document, dict) else {}
    lines = [ln for ln in (ocr_lines or []) if isinstance(ln, dict)]
    if not lines:
        # Allow goldens / callers to attach lines on the document itself.
        raw = doc.get("ocr_lines") or doc.get("ocr_menu_hints") or []
        lines = [ln for ln in raw if isinstance(ln, dict)]
    if not lines:
        return doc

    objects = [o for o in (doc.get("objects") or []) if isinstance(o, dict)]
    seen = {
        str(o.get("text") or o.get("label") or "").strip().lower()
        for o in objects
        if _label_looks_like_menu_verb(str(o.get("text") or o.get("label") or ""))
    }
    added = 0
    for line in lines:
        text = str(line.get("text") or line.get("label") or "").strip()
        if not _label_looks_like_menu_verb(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        point = line.get("point")
        bounds = line.get("bounds")
        if point is None and isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
            try:
                x, y, w, h = (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
                point = [x + w / 2.0, y + h / 2.0]
            except (TypeError, ValueError):
                point = None
        if point is None or not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            pt = [float(point[0]), float(point[1])]
        except (TypeError, ValueError):
            continue
        obj: Dict[str, Any] = {
            "text": text,
            "label": text,
            "kind": "menu_item",
            "is_menu_item": True,
            "point": pt,
            "geometry_source": "ocr_menu",
        }
        if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
            try:
                obj["bounds"] = [float(x) for x in bounds[:4]]
            except (TypeError, ValueError):
                pass
        objects.append(obj)
        seen.add(key)
        added += 1
    if added:
        doc["objects"] = objects
        doc["ocr_menu_enriched"] = True
    return doc


def reconcile_frontier(
    frontier: Any,
    *,
    document: Optional[Dict[str, Any]] = None,
    execution_state: Any = None,
    last_action_family: str = "",
) -> Any:
    """Apply the critic's accepted reality to a freshly built action topology.

    Two moves, both driven by evidence the runtime measured rather than by the
    model's say-so: controls proven inert are withdrawn from the live set (and
    reported as excluded, with the reason, so the perceptor learns rather than
    silently loses an option), and a confirmed reveal promotes the latent
    controls it put on screen to observed.
    """
    if frontier is None:
        return frontier
    document = document if isinstance(document, dict) else {}
    surface = _norm_surface(document.get("surface") or getattr(frontier, "surface", ""))
    family = _norm_label(last_action_family)
    handoff = _reveal_handoff_active(execution_state)
    has_menu_layer = _document_has_action_menu_layer(document)

    # Promote when a reveal probe just ran (handoff) or last action was
    # reveal_actions, and the accepted document shows a revealed surface / menu
    # layer / still-active handoff (lossy flat enum often stays conversation).
    # Handoff alone is enough for the family check: post-accept promote may run
    # after the plan step was cleared but while incomplete_reveal is still owed.
    should_promote = (family == "reveal_actions" or handoff) and (
        surface in _REVEALED_SURFACES or handoff or has_menu_layer
    )
    if should_promote:
        # Without a flat surface flip, only promote menu-shaped / control-labeled
        # objects so chat bubbles are not mistaken for Forward/Reply controls.
        prefer_menu = surface not in _REVEALED_SURFACES
        grounded = _grounded_from_objects(document, prefer_menu=prefer_menu)
        if not grounded and not prefer_menu:
            grounded = _grounded_from_objects(document, prefer_menu=False)
        # VLM often tags Forward without kind=menu_item after a reveal probe.
        # Do not treat conversation chrome like "Forwarded: …" as the Forward CTA
        # (150708 window-pixel false positive).
        if prefer_menu and not grounded:
            grounded = [
                g
                for g in _grounded_from_objects(document, prefer_menu=False)
                if _label_looks_like_menu_verb(str(getattr(g, "label", "") or ""))
            ]
        if grounded:
            try:
                from plugin.agent.affordance_frontier import (
                    ground_revealed,
                    publish_grounded_affordance_set,
                )
                from types import SimpleNamespace

                ground_revealed(frontier, SimpleNamespace(actions=grounded))
                publish_grounded_affordance_set(execution_state, frontier)
            except Exception:
                pass
    else:
        # Keep the durable substrate in sync even when no new promote ran.
        try:
            from plugin.agent.affordance_frontier import publish_grounded_affordance_set

            publish_grounded_affordance_set(execution_state, frontier)
        except Exception:
            pass

    dead = [
        item
        for item in (getattr(execution_state, "dead_affordances", None) or [])
        if isinstance(item, dict) and item.get("key")
    ]
    if not dead:
        return frontier
    dead_keys = {str(item["key"]) for item in dead}

    def _is_dead(affordance: Any) -> Optional[Dict[str, str]]:
        key = affordance_key(
            surface,
            getattr(affordance, "family", ""),
            getattr(affordance, "target_label", ""),
        )
        if key not in dead_keys:
            return None
        for item in dead:
            if str(item["key"]) == key:
                return item
        return None

    excluded = list(getattr(frontier, "excluded_actions", None) or [])
    for bucket in ("observed_actions", "latent_actions", "probe_actions"):
        keep = []
        for affordance in list(getattr(frontier, bucket, None) or []):
            record = _is_dead(affordance)
            if record is None:
                keep.append(affordance)
                continue
            excluded.append(
                {
                    "action": f"{record['family']}:{record['target']}" if record["target"] else record["family"],
                    "reason": record["reason"],
                }
            )
        setattr(frontier, bucket, keep)
    frontier.excluded_actions = excluded
    return frontier


def _accept_layers(
    prior_doc: Dict[str, Any],
    accepted: Dict[str, Any],
    *,
    last_action: str = "",
    surface: str = "",
) -> Optional[CriticDecision]:
    """Validate / merge layer stack push-pop into ``accepted`` when enabled.

    Returns a CriticDecision when layers are touched; None when the feature is
    off or there is nothing to do. Never invents menu items — only enforces
    permanence (container stays under overlay) and normalizes the stack.
    """
    try:
        from plugin.agent.scene_layers import (
            ACTION_MENU,
            OVERLAY_ROLES,
            flat_objects,
            layered_perception_enabled,
            layers_from_flat,
            layers_to_dicts,
            merge_permanence,
            normalize_layers,
        )
    except Exception:
        return None
    if not layered_perception_enabled():
        return None

    prior_layers = normalize_layers(prior_doc.get("layers")) if prior_doc else []
    raw_new = accepted.get("layers")
    if raw_new:
        new_layers = normalize_layers(raw_new)
        verdict = "accept"
        reason = "proposal layers normalized; permanence merge applied"
    else:
        new_layers = layers_from_flat(
            accepted.get("surface") or surface,
            accepted.get("open_conversation"),
            accepted.get("objects"),
        )
        verdict = "edit"
        reason = "derived layers from flat surface; permanence merge applied"

    action = _norm_label(last_action)
    top_role = new_layers[-1].role if new_layers else ""
    if top_role in OVERLAY_ROLES and action not in {
        "reveal_actions",
        "context_click",
        "invoke_affordance",
        "hover",
        "",
    }:
        reason = f"{reason}; overlay top={top_role} after action={action or 'none'}"

    merged = merge_permanence(prior_layers, new_layers)
    if not merged:
        return None
    accepted["layers"] = layers_to_dicts(merged)
    try:
        union = flat_objects(merged)
        if union:
            prior_texts = {
                str(o.get("text") or o.get("label") or "").strip().lower()
                for o in (accepted.get("objects") or [])
                if isinstance(o, dict)
            }
            menu_added = any(
                str(o.get("kind") or "").lower() in _MENU_KINDS
                or _label_looks_like_menu_verb(
                    str(o.get("text") or o.get("label") or "")
                )
                for o in union
                if str(o.get("text") or "").strip().lower() not in prior_texts
            )
            if menu_added or not accepted.get("objects"):
                accepted["objects"] = union[:12]
    except Exception:
        pass

    has_menu = any(l.role == ACTION_MENU for l in merged)
    has_base = any(not l.is_overlay for l in merged)
    if has_menu and not has_base and prior_layers:
        verdict = "edit"
        reason = "overlay push restored occluded base from prior (permanence)"
    return CriticDecision(
        field="layers",
        verdict=verdict,
        reason=reason,
        prior=len(prior_layers),
        proposed=len(new_layers),
        accepted=len(merged),
    )


def promote_frontier_after_accept(
    execution_state: Any,
    *,
    accepted_document: Optional[Dict[str, Any]] = None,
    last_action_family: str = "",
    ocr_lines: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Promote revealed controls from the *accepted* post-look document.

    Timing fix for multi-pass discovery: ``_frontier_for_packet`` reconciles
    against the *prior* document before stage-1 writes menu objects. After
    ``persist_world_document`` accepts the new reading, call this so Forward
    (etc.) enter ``affordance_set`` while the overlay is still live.

    Under an active reveal handoff, OCR menu verbs may enrich the *document*
    first (geometry from OCR bounds). Still no OCR→affordance_set invent path.
    """
    status: Dict[str, Any] = {"promoted": False, "grounded": 0, "ocr_enriched": False}
    if execution_state is None:
        return status
    doc = accepted_document
    if not isinstance(doc, dict):
        doc = getattr(execution_state, "unified_world_document", None)
    if not isinstance(doc, dict):
        return status

    if _reveal_handoff_active(execution_state):
        lines = ocr_lines
        if lines is None:
            lines = getattr(execution_state, "last_overlay_ocr_menu", None)
        enriched = enrich_document_menu_verbs_from_ocr(doc, lines)
        if enriched.get("ocr_menu_enriched"):
            status["ocr_enriched"] = True
            doc = enriched
            try:
                execution_state.unified_world_document = dict(doc)
            except Exception:
                pass

    family = _norm_label(last_action_family)
    if not family:
        step = getattr(execution_state, "last_plan_step", None)
        family = _norm_label(
            getattr(step, "action_family", "") or getattr(execution_state, "last_action", "")
        )
    if not family and _reveal_handoff_active(execution_state):
        family = "reveal_actions"

    try:
        from plugin.agent.affordance_frontier import (
            Affordance,
            AffordanceFrontier,
            STATUS_LATENT,
            finalize_reveal_handoff,
            grounded_affordance_set_of,
        )
    except Exception:
        return status

    stored = getattr(execution_state, "last_affordance_frontier", None)
    if hasattr(stored, "observed_actions") and hasattr(stored, "latent_actions"):
        frontier = stored
    else:
        # Seed a latent Forward so ground_revealed can flip it; also ingest any
        # menu items not prelisted. Packet dicts are not rehydrated as objects.
        seed_surface = ""
        if isinstance(stored, dict):
            seed_surface = str(stored.get("surface") or "")
        frontier = AffordanceFrontier(
            surface=seed_surface or str(doc.get("surface") or ""),
            latent_actions=[
                Affordance(
                    id="goal_fwd",
                    family="invoke_affordance",
                    status=STATUS_LATENT,
                    target_label="Forward",
                )
            ],
        )

    try:
        frontier = reconcile_frontier(
            frontier,
            document=doc,
            execution_state=execution_state,
            last_action_family=family or "reveal_actions",
        )
        finalize_reveal_handoff(execution_state, frontier)
    except Exception:
        return status

    grounded = grounded_affordance_set_of(execution_state)
    status["grounded"] = len(grounded)
    status["promoted"] = bool(grounded)
    try:
        if hasattr(frontier, "to_packet"):
            execution_state.last_affordance_frontier = frontier.to_packet()
        elif isinstance(frontier, dict):
            execution_state.last_affordance_frontier = frontier
    except Exception:
        pass
    return status
