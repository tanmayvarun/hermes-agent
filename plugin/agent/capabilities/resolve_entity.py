"""Resolve which candidate matches a goal referent — judgment, not a click script.

On a picker / list, several rows can share a name (``Tanmay``, ``Tanmay (you)``,
groups, near-homophones). Choosing among them is semantic resolution over a
``candidate_set`` substrate, parallel to ``compose_search_query`` over task
evidence:

    resolve_entity(referent, candidates) → which addressable row
    open_entity(chosen)                  → navigate / select it (mechanism)

The capability never hardcodes WhatsApp ``(you)`` as the only rule; heuristics
and an optional LLM ranker use label evidence. Outcomes report the chosen
label and why — they do not claim the forward/send succeeded.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable

from plugin.agent.capabilities.base import CapabilityOutcome

logger = logging.getLogger(__name__)

_RESOLVE_SYSTEM = (
    "You resolve which UI candidate row matches a goal referent. "
    "You receive a referent string, a role (destination/source/…), and an "
    "unordered list of candidate labels with optional hints. "
    "Return ONLY JSON "
    '{"candidates":[{"label":"...","score":0-1,"why":"..."}],"chosen":"..."}. '
    "Prefer exact / alias matches over weak substring hits. "
    "Self markers like (you), (me), or 'You' count as evidence that the row "
    "is the current user when the referent matches the base name. "
    "Never invent a label that is not in the candidate list. "
    "Never invent click scripts."
)


@runtime_checkable
class EntityResolver(Protocol):
    def resolve(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
        """Return ``{"candidates":[...], "chosen": str}``."""


@dataclass
class ResolveBrief:
    """Evidence bag for entity resolution — not a motor target."""

    referent: str = ""
    role: str = "destination"
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    goal_tokens: List[str] = field(default_factory=list)
    notes: str = ""


def _clean_label(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _base_name(label: str) -> str:
    text = _clean_label(label)
    # Strip trailing self / role markers: "Tanmay (you)", "Tanmay - You"
    text = re.sub(r"\s*[\(\[]\s*(you|me|self)\s*[\)\]]\s*$", "", text, flags=re.I)
    text = re.sub(r"\s*[-–—]\s*(you|me|self)\s*$", "", text, flags=re.I)
    return text.strip()


def _row_contact_name(label: str) -> str:
    """The contact-name head of a search/picker row, without its message preview.

    WhatsApp search-result and picker rows append the last-message preview to the
    contact name, flattened into one label:

        "Pallavi - You: https://www.zarooratwala.com/..."

    Matching the whole string against the referent "Pallavi" scores it as mere
    containment and abstains — the loop that stalled the ZarooratWala run, where
    the *correct* row was refused because its preview happened to carry the goal
    URL. Cutting at the first preview separator lets the resolver match the name
    the row actually belongs to. A plain multi-token name with no preview marker
    (e.g. "Pallavi Ather Gen3") has nothing to cut, so the containment guard for
    genuinely different contacts still applies.
    """
    text = _clean_label(label)
    cuts: List[int] = []
    # 1) An explicit " - " / dash separator between name and preview.
    for sep in (" - ", " – ", " — "):
        idx = text.find(sep)
        if idx > 0:
            cuts.append(idx)
    # 2) A "Name: preview" / "You: …" colon separator (colon followed by space;
    #    a bare time like "12:34" has no trailing space and is left alone).
    colon = re.search(r":\s", text)
    if colon and colon.start() > 0:
        cuts.append(colon.start())
    # 3) An embedded URL, even when nothing separated it from the name.
    url = re.search(r"https?://", text, flags=re.I)
    if url and url.start() > 0:
        cuts.append(url.start())
    if cuts:
        text = text[: min(cuts)]
    return text.strip().rstrip(":").strip() or _clean_label(label)


# Below this, the best candidate is not good enough to act on. Abstaining
# costs a turn; picking wrong sends the message to a stranger, and nothing
# downstream can undo that. Overridable so a run can be A/B'd against the old
# always-pick behaviour without editing code.
_CHOICE_FLOOR = float(os.getenv("HERMES_RESOLVE_FLOOR", "0.5"))

# Threads whose title merely contains a person's name: "Aakash <> Tanmay",
# "Tanmay Saurabh Connect", "Weight tracker". Forwarding to one of these is the
# single most expensive mistake available on a picker full of near-matches.
_GROUP_SHAPES = ("<>", "<->", "&", ",", " + ", " and ", " group")
_PERSON_ROLES = {"destination", "source", "contact", "recipient"}


def _looks_like_group(label: str, hints: Any = None) -> bool:
    low = _clean_label(label).lower()
    if any(shape in low for shape in _GROUP_SHAPES):
        return True
    marks = [str(h).lower() for h in (hints or [])]
    return "group" in marks


# Object kinds that are not addressable rows to open. The search *input* field
# often carries a label identical to the query ("Pallavi zarooratwala"), so it
# out-scores the real result row on text match and, when "opened", does nothing
# — the loop that stalled the ZarooratWala run. A resolve candidate must be a
# thing you can open, not the box you typed into.
_NON_OPENABLE_KINDS = {
    "search_input",
    "search_field",
    "search_bar",
    "search",
    "text_field",
    "textfield",
    "input",
    "field",
    "composer",
    "message_input",
    "textbox",
    # Content under a picker/list is not a contact row — keeping it out stops a
    # goal-matched message from polluting destination resolve_entity candidates.
    "message",
    "message_link_preview",
    "link",
    "attachment",
    "media",
    "image",
    "video",
    "audio",
    "document",
    "button",
    "label",
    "status",
}


def _is_openable_kind(kind: Any) -> bool:
    return str(kind or "").strip().lower() not in _NON_OPENABLE_KINDS


def _self_marker(label: str) -> bool:
    low = _clean_label(label).lower()
    return bool(
        re.search(r"\((you|me|self)\)", low)
        or re.search(r"\b(you|me|self)\b\s*$", low)
        or low in {"you", "me"}
    )


def candidates_from_context(
    *,
    features: Any = None,
    world_document: Optional[Dict[str, Any]] = None,
    explicit: Optional[Sequence[Any]] = None,
) -> List[Dict[str, Any]]:
    """Build a candidate_set from world objects / feature extras."""
    rows: List[Dict[str, Any]] = []
    seen = set()

    def add(label: Any, **extra: Any) -> None:
        text = _clean_label(label)
        if not text:
            return
        if not _is_openable_kind(extra.get("kind")):
            # The search box / composer is not a row you can open; excluding it
            # keeps a query-shaped input from out-ranking the real result.
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        entry = {"label": text, **extra}
        if _self_marker(text):
            entry.setdefault("hints", [])
            if isinstance(entry["hints"], list) and "self" not in entry["hints"]:
                entry["hints"] = list(entry["hints"]) + ["self"]
        rows.append(entry)

    for item in explicit or []:
        if isinstance(item, str):
            add(item)
        elif isinstance(item, dict):
            add(
                item.get("label") or item.get("text") or item.get("name"),
                hints=list(item.get("hints") or []),
                point=item.get("point"),
                id=item.get("id"),
                kind=item.get("kind"),
            )

    doc = world_document if isinstance(world_document, dict) else {}
    for obj in doc.get("objects") or []:
        if isinstance(obj, dict):
            add(
                obj.get("text") or obj.get("label") or obj.get("name"),
                hints=list(obj.get("hints") or []),
                point=obj.get("point"),
                id=obj.get("id"),
                kind=obj.get("kind"),
            )

    extras = {}
    if features is not None and isinstance(getattr(features, "extras", None), dict):
        extras = features.extras
    for key in (
        "visible_contacts",
        "search_result_rows",
        "contact_candidates",
        "destination_candidates",
        "picker_rows",
    ):
        raw = extras.get(key) or []
        if not isinstance(raw, list):
            continue
        for item in raw[:24]:
            if isinstance(item, str):
                add(item)
            elif isinstance(item, dict):
                add(
                    item.get("text") or item.get("name") or item.get("label"),
                    hints=list(item.get("hints") or []),
                    point=item.get("point"),
                    id=item.get("id") or item.get("entity_id"),
                )
    return rows


def brief_from_context(
    goal: Any,
    *,
    referent: str = "",
    role: str = "destination",
    features: Any = None,
    world_document: Optional[Dict[str, Any]] = None,
    candidates: Optional[Sequence[Any]] = None,
) -> ResolveBrief:
    ref = _clean_label(
        referent
        or (
            getattr(goal, "target_contact", None)
            if role == "destination"
            else getattr(goal, "contact", None)
        )
        or getattr(goal, "target_contact", None)
        or getattr(goal, "contact", None)
        or ""
    )
    tokens: List[str] = []
    for attr in ("contact", "target_contact", "link_query"):
        val = _clean_label(getattr(goal, attr, None))
        if val and val not in tokens:
            tokens.append(val)
    notes = ""
    if features is not None and isinstance(getattr(features, "extras", None), dict):
        notes = str(features.extras.get("scene_summary") or "")[:200]
    return ResolveBrief(
        referent=ref,
        role=role or "destination",
        candidates=candidates_from_context(
            features=features,
            world_document=world_document,
            explicit=candidates,
        ),
        goal_tokens=tokens,
        notes=notes,
    )


def open_matches_referent(open_title: str, referent: str) -> bool:
    """Whether an open conversation title is an acceptable match for a referent.

    Exact / base-name / self-marker matches count. Mere substring containment
    (``Pallavi Ather Gen3`` for referent ``Pallavi``) does **not**.
    Multi-party headers (``Pallavi, Papaji, Rekha, You``) are membership lists,
    not conversation identity — never treat them as the referent's chat.
    """
    title = _clean_label(open_title)
    ref = _clean_label(referent)
    if not title or not ref:
        return False
    # Group participant CSVs: membership ≠ open identity (live 214626).
    parts = [p.strip() for p in title.split(",") if p.strip()]
    if len(parts) >= 2:
        low_parts = [p.lower() for p in parts]
        if "you" in low_parts or len(parts) >= 3:
            return False
    if title.lower() == ref.lower():
        return True
    title_base = _base_name(title).lower()
    ref_base = _base_name(ref).lower()
    if title_base and ref_base and title_base == ref_base:
        return True
    return False


def allow_keyboard_search_open(
    *,
    hint: str,
    target_point: Any = None,
    open_name: str = "",
    on_search_surface: bool = False,
    search_empty: bool = False,
) -> bool:
    """Last-resort Down+Return only when no judgment target exists.

    A model-supplied point (or a resolved label open) must not be overridden by
    WhatsApp's top search hit.
    """
    if not str(hint or "").strip():
        return False
    if str(open_name or "").strip():
        return False
    if not on_search_surface or search_empty:
        return False
    if target_point is not None:
        return False
    return True


# Roles whose downstream action merely *opens* something (reversible): a wrong
# open costs a turn but is undoable. Everything else (sending / forwarding to a
# destination) is irreversible and gets a higher bar before the module trusts
# its own deterministic pick without a semantic (LLM) confirmation.
_REVERSIBLE_ROLES = {"source", "contact", "open", "navigate"}

# Consequence-scaled bars the module applies to its *own* confidence. Reversible
# resolution can act on a modest lead; irreversible resolution demands a strong,
# clearly-leading match or the module consults an LLM over the candidates.
_REVERSIBLE_TOP_FLOOR = 0.5
_REVERSIBLE_MARGIN_FLOOR = 0.15
_IRREVERSIBLE_TOP_FLOOR = 0.75
_IRREVERSIBLE_MARGIN_FLOOR = 0.35
# Below this the LLM's own pick is treated as residual ambiguity, and for an
# irreversible action the module abstains to the user rather than guess.
_LLM_ACT_FLOOR = 0.5


def _is_irreversible(role: Any) -> bool:
    return str(role or "").strip().lower() not in _REVERSIBLE_ROLES


def resolution_evidence(ranked: Sequence[Dict[str, Any]], referent: str = "") -> Dict[str, Any]:
    """Summarise a ranking into the signals the module judges its own accuracy on.

    The deterministic ranker proposes; it does not get to declare itself correct.
    These are the signals its confidence policy reads: how strong the top match
    is, how far it leads the runner-up, whether the top row carries a decisive
    self/(you) identity marker, whether it is the only strong (name-identity)
    match, and how many candidates competed. A bare exact string is not a true
    positive — a strong, clearly-leading match is.
    """
    rows = [r for r in (ranked or []) if isinstance(r, dict)]
    if not rows:
        return {
            "top_score": 0.0,
            "margin": 0.0,
            "match_type": "none",
            "strong": False,
            "unique_strong": False,
            "top_self": False,
            "candidates": 0,
        }
    top = rows[0]
    top_score = float(top.get("score") or 0.0)
    runner = float(rows[1].get("score") or 0.0) if len(rows) > 1 else 0.0
    strong_rows = [r for r in rows if r.get("strong")]
    return {
        "top_score": round(top_score, 3),
        "margin": round(top_score - runner, 3),
        "match_type": str(top.get("match_type") or "none"),
        "strong": bool(top.get("strong")),
        "unique_strong": len(strong_rows) == 1 and bool(top.get("strong")),
        "top_self": bool(top.get("self")),
        "candidates": len(rows),
    }


def deterministic_confidence(evidence: Dict[str, Any]) -> float:
    """The module's calibrated confidence in its own deterministic pick, 0..1.

    This is *self-assessment* — the whole point of a robust skill is that it
    knows when it is right. A self/(you) identity marker is decisive; a strong
    name-identity match scales with score and margin; containment-only matches
    stay low no matter how they rank.
    """
    ev = evidence or {}
    top = float(ev.get("top_score") or 0.0)
    margin = float(ev.get("margin") or 0.0)
    strong = bool(ev.get("strong"))
    if ev.get("top_self") and strong:
        return round(min(1.0, 0.9 + 0.1 * min(1.0, margin / 0.2)), 3)
    if not strong:
        return round(min(0.45, 0.25 + 0.4 * min(1.0, margin)), 3)
    conf = 0.55 + 0.25 * min(1.0, top) + 0.2 * min(1.0, margin / 0.5)
    if ev.get("unique_strong"):
        conf += 0.05
    return round(min(1.0, conf), 3)


def is_confident(evidence: Dict[str, Any], *, irreversible: bool) -> bool:
    """Whether the module trusts its own pick enough to skip the LLM.

    Self-marker identity is decisive in either consequence class. Otherwise an
    irreversible action needs a strong, clearly-leading match; a reversible one
    accepts a smaller lead because a wrong open is undoable. This is the single
    place the fast-path/escalate boundary lives — inside the skill, not the brain.
    """
    ev = evidence or {}
    if not ev.get("strong"):
        return False
    if ev.get("top_self"):
        return True
    top = float(ev.get("top_score") or 0.0)
    margin = float(ev.get("margin") or 0.0)
    if irreversible:
        return top >= _IRREVERSIBLE_TOP_FLOOR and margin >= _IRREVERSIBLE_MARGIN_FLOOR
    return top >= _REVERSIBLE_TOP_FLOOR and margin >= _REVERSIBLE_MARGIN_FLOOR


def heuristic_resolve(brief: ResolveBrief) -> Dict[str, Any]:
    """Deterministic ranker — enough for (you)/alias cases without an LLM."""
    referent = _clean_label(brief.referent).lower()
    ref_base = _base_name(brief.referent).lower()
    ranked: List[Dict[str, Any]] = []
    for item in brief.candidates:
        label = _clean_label(item.get("label"))
        if not label:
            continue
        low = label.lower()
        # Match against the contact-name head, not the appended message preview,
        # so a search-result row "Pallavi - You: <url>" is recognised as Pallavi.
        row_name = _row_contact_name(label)
        name_low = row_name.lower()
        base = _base_name(row_name).lower()
        score = 0.0
        why = []
        # match_type records *how* the row matched, so the executive can judge
        # confidence from the kind of evidence, not just the scalar score.
        match_type = "none"
        if referent and low == referent:
            score += 1.0
            why.append("exact label match")
            match_type = "exact"
        elif referent and name_low == referent:
            score += 0.95
            why.append("search-row contact-name exact match")
            match_type = "contact_name"
        elif ref_base and base == ref_base:
            score += 0.75
            why.append("base-name match")
            match_type = "base"
        elif referent and referent in low:
            score += 0.45
            why.append("substring match")
            match_type = "substring"
            # Longer multi-token labels that merely contain the referent are weak
            # (e.g. "Pallavi Ather Gen3" for referent "Pallavi").
            if base != ref_base and len(low.split()) > len(referent.split()):
                score -= 0.3
                why.append("penalize longer substring-only")
        elif ref_base and ref_base in low:
            score += 0.35
            why.append("base substring")
            match_type = "base_substring"
            if base != ref_base and len(low.split()) > len(ref_base.split()):
                score -= 0.25
                why.append("penalize longer base-substring")
        self_applied = False
        if _self_marker(label) and ref_base and (base == ref_base or ref_base in base):
            score += 0.4
            why.append("self marker with matching base")
            self_applied = True
        hints = item.get("hints") or []
        if isinstance(hints, list) and "self" in hints and ref_base and base == ref_base:
            score += 0.25
            why.append("self hint")
            self_applied = True
        if (
            low != referent
            and str(brief.role or "").strip().lower() in _PERSON_ROLES
            and _looks_like_group(label, hints)
        ):
            score -= 0.4
            why.append("multi-party thread, not the person named")
        if score <= 0:
            continue
        # A "strong" match is name-identity evidence (exact / contact-name /
        # base / self), not mere containment. The executive trusts strong,
        # unique, high-margin matches; everything else is a candidate for LLM
        # semantic resolution.
        strong = match_type in {"exact", "contact_name", "base"} or self_applied
        ranked.append(
            {
                "label": label,
                "score": score,
                "match_type": match_type,
                "strong": strong,
                "self": self_applied,
                "why": "; ".join(why),
                "point": item.get("point"),
                "id": item.get("id"),
            }
        )
    # Prefer higher uncapped score so base+self can beat bare exact ties.
    ranked.sort(
        key=lambda r: (
            -float(r["score"]),
            -int(_self_marker(str(r["label"]))),
            len(str(r["label"])),
        )
    )
    # Summarise the shape of the ranking *before* capping, so the margin between
    # the top pick and its runner-up survives (two rows capped to 1.0 would look
    # identical). This is the evidence the executive reads to decide whether the
    # fast path is a confident true positive or must escalate.
    evidence = resolution_evidence(ranked, brief.referent)
    for item in ranked:
        item["score"] = round(min(1.0, float(item["score"])), 3)
    if not ranked:
        return {
            "candidates": [],
            "chosen": "",
            "abstained": True,
            "reason": "no candidate matched",
            "evidence": evidence,
        }
    best = ranked[0]
    if float(best["score"]) < _CHOICE_FLOOR:
        # Something contains the name, but nothing *is* it. The caller's
        # no-match path can narrow the query or ask for evidence; there is no
        # recovery from having forwarded to the wrong thread.
        return {
            "candidates": ranked,
            "chosen": "",
            "abstained": True,
            "reason": (
                f"best candidate {best['label']!r} scores {best['score']} "
                f"on containment alone; below the floor to act"
            ),
            "evidence": evidence,
        }
    return {"candidates": ranked, "chosen": best["label"], "evidence": evidence}


@dataclass
class LlmEntityResolver:
    """Optional short LLM call; falls back to heuristic on failure."""

    timeout_s: float = 60.0

    def resolve(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
        from plugin.agent.perception_synthesis import _call_llm_hard_timeout
        from plugin.agent.reasoning_consultation import consult_reasoning

        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Choose the best candidate for the referent.\n"
                    + json.dumps(packet, ensure_ascii=False, default=str)[:6000]
                ),
            },
        ]
        try:
            consultation = consult_reasoning(
                "decision",
                messages,
                usecase="resolve_entity",
                caller=lambda **kwargs: _call_llm_hard_timeout(self.timeout_s, **kwargs),
                call_kwargs={"timeout": self.timeout_s},
                temperature=0.1,
                max_tokens=256,
            )
        except Exception as exc:
            logger.warning("resolve_entity LLM failed: %s", exc)
            return {}
        parsed = getattr(consultation, "parsed", None) or {}
        if isinstance(parsed, dict) and (parsed.get("chosen") or parsed.get("candidates")):
            return parsed
        raw = str(getattr(consultation, "raw_response", "") or "")
        try:
            return json.loads(raw)
        except Exception:
            match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            if not match:
                return {}
            try:
                return json.loads(match.group(0))
            except Exception:
                return {}


def _top_llm_score(sanitized: Dict[str, Any]) -> float:
    """Best numeric confidence the LLM assigned among returned candidates.

    Absent explicit scores, treat a returned choice as moderately confident
    (0.7) — enough to act on a reversible open, still checkable against the
    irreversible act floor.
    """
    scores: List[float] = []
    for item in sanitized.get("candidates") or []:
        if isinstance(item, dict) and item.get("score") is not None:
            try:
                scores.append(float(item["score"]))
            except (TypeError, ValueError):
                continue
    if scores:
        return max(scores)
    return 0.7 if _clean_label(sanitized.get("chosen")) else 0.0


def _sanitize_choice(payload: Dict[str, Any], allowed: Sequence[str]) -> Dict[str, Any]:
    allow = {_clean_label(x): x for x in allowed if _clean_label(x)}
    allow_l = {k.lower(): v for k, v in allow.items()}
    chosen = _clean_label(payload.get("chosen"))
    if chosen.lower() not in allow_l:
        # Try to map to a listed candidate from ranked list.
        for item in payload.get("candidates") or []:
            if isinstance(item, dict):
                label = _clean_label(item.get("label"))
                if label.lower() in allow_l:
                    chosen = allow_l[label.lower()]
                    break
        else:
            chosen = ""
    else:
        chosen = allow_l[chosen.lower()]
    queries = []
    for item in payload.get("candidates") or []:
        if isinstance(item, dict):
            label = _clean_label(item.get("label"))
            if label.lower() in allow_l:
                queries.append(
                    {
                        "label": allow_l[label.lower()],
                        "score": item.get("score"),
                        "why": str(item.get("why") or "")[:200],
                    }
                )
    return {"chosen": chosen, "candidates": queries}


_RESOLUTION_METHODS = ("deterministic", "llm", "deterministic_fallback", "abstain")


@dataclass
class ResolutionRequest:
    """A text-first resolution job — no perception, no UI, just text.

    ``candidates`` is the *high-level representation* the executive has already
    perceived: a list of label strings or ``{"label", "hints", "point", "id"}``
    dicts. The skill resolves over this text; if fresh perception is needed, the
    executive performs it earlier and passes the result in here.
    """

    referent: str = ""
    candidates: List[Any] = field(default_factory=list)
    # "reversible" (a wrong pick is undoable, e.g. open/switch) or "irreversible"
    # (a wrong pick cannot be taken back, e.g. send/forward/delete). Left blank,
    # it is inferred from ``role``.
    consequence: str = ""
    role: str = ""
    goal_tokens: List[str] = field(default_factory=list)
    context: str = ""

    @property
    def irreversible(self) -> bool:
        c = str(self.consequence or "").strip().lower()
        if c == "irreversible":
            return True
        if c == "reversible":
            return False
        return _is_irreversible(self.role)


@dataclass
class ResolutionResult:
    """What the skill decided, and how sure it is — for the brain to evaluate.

    ``method`` records the path taken (deterministic fast path, LLM semantic
    resolution, deterministic fallback after an LLM miss, or abstain) so the
    executive's outer evaluation can see *how* the answer was reached, not just
    what it was.
    """

    chosen: str = ""
    confidence: float = 0.0
    method: str = "abstain"
    escalated: bool = False
    needs_user: bool = False
    ranked: List[Dict[str, Any]] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chosen": self.chosen,
            "confidence": round(float(self.confidence or 0.0), 3),
            "method": self.method,
            "escalated": self.escalated,
            "needs_user": self.needs_user,
            "evidence": dict(self.evidence or {}),
            "rationale": self.rationale,
        }


@dataclass
class MatchResult:
    """The pure semantic-match core's output: a ranking, nothing decided yet.

    ``match`` is the shared primitive under both cardinality policies. It ranks
    candidates by closeness to the query and reports the module's own confidence
    in the top; it does *not* pick, threshold, consult an LLM, or abstain — those
    are policy, owned by ``resolve_one`` / ``resolve_many``.
    """

    ranked: List[Dict[str, Any]] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0

    def top(self) -> Optional[Dict[str, Any]]:
        return self.ranked[0] if self.ranked else None


@dataclass
class MultiResolution:
    """Result of resolving *many* matching entities (recall-oriented).

    Unlike ``resolve_one`` there is no single-choice abstain: returning several
    (or zero) matches is the expected shape. The caller decides what to do with
    the set.
    """

    matches: List[str] = field(default_factory=list)
    ranked: List[Dict[str, Any]] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    method: str = "deterministic"
    escalated: bool = False
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matches": list(self.matches),
            "count": len(self.matches),
            "method": self.method,
            "escalated": self.escalated,
            "evidence": dict(self.evidence or {}),
            "rationale": self.rationale,
        }


def _normalize_candidates(raw: Sequence[Any]) -> List[Dict[str, Any]]:
    """Accept text or dicts and return uniform ``{label, hints, point, id}`` rows."""
    rows: List[Dict[str, Any]] = []
    for item in raw or []:
        if isinstance(item, str):
            label = _clean_label(item)
            if label:
                rows.append({"label": label, "hints": []})
        elif isinstance(item, dict):
            label = _clean_label(item.get("label") or item.get("text") or item.get("name"))
            if label:
                rows.append(
                    {
                        "label": label,
                        "hints": list(item.get("hints") or []),
                        "point": item.get("point"),
                        "id": item.get("id") or item.get("entity_id"),
                    }
                )
    return rows


def _default_resolver() -> "LlmEntityResolver":
    """The LLM the skill consults when it decides it is not sure enough.

    Injected in tests; constructed lazily in production. Failures degrade to {}
    inside ``LlmEntityResolver.resolve``, so the skill never hangs on it.
    """
    return LlmEntityResolver()


def match(
    query: str,
    candidates: Sequence[Any],
    *,
    role: str = "",
    goal_tokens: Sequence[str] = (),
    context: str = "",
) -> MatchResult:
    """Rank candidates by closeness to ``query`` — the pure matcher primitive.

    Deterministic and side-effect-free: no LLM, no cardinality, no abstain. This
    is the cheap general prior both cardinality policies build on. Only rows that
    relate to the query at all are returned (score > 0), best first.
    """
    referent = _clean_label(query)
    cands = _normalize_candidates(candidates)
    if not referent or not cands:
        return MatchResult(ranked=[], evidence=resolution_evidence([], referent), confidence=0.0)
    brief = ResolveBrief(
        referent=referent,
        role=role or "source",
        candidates=cands,
        goal_tokens=list(goal_tokens or []),
        notes=context or "",
    )
    heuristic = heuristic_resolve(brief)
    ranked = heuristic.get("candidates") or []
    evidence = heuristic.get("evidence") or resolution_evidence(ranked, referent)
    return MatchResult(ranked=ranked, evidence=evidence, confidence=deterministic_confidence(evidence))


def _ranked_from_llm(sanitized: Dict[str, Any], cands: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build a ranked list from an LLM payload, carrying candidate metadata."""
    by_label = {c["label"].lower(): c for c in cands}
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in sanitized.get("candidates") or []:
        label = _clean_label(item.get("label"))
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        base = by_label.get(label.lower(), {"label": label})
        out.append(
            {
                "label": base.get("label", label),
                "score": float(item.get("score") or 0.0),
                "match_type": "llm",
                "strong": True,
                "self": False,
                "why": str(item.get("why") or "semantic match"),
                "point": base.get("point"),
                "id": base.get("id"),
            }
        )
    return out


def resolve_one(
    request: ResolutionRequest,
    *,
    resolver: Optional[EntityResolver] = None,
) -> ResolutionResult:
    """Resolve to a *single* best entity — precision-oriented, safety-gated.

    The skill owns its own accuracy judgement: it tries the deterministic match
    and, by itself, decides whether that top pick is trustworthy. When it is not
    sure enough it consults an LLM over the candidates; when even that leaves an
    irreversible action ambiguous it abstains to the user. The executive is the
    outer evaluator of the result, not the arbiter of this internal decision.
    """
    referent = _clean_label(request.referent)
    cands = _normalize_candidates(request.candidates)
    if not referent:
        return ResolutionResult(method="abstain", needs_user=True, rationale="no referent supplied")
    if not cands:
        return ResolutionResult(method="abstain", needs_user=True, rationale="empty candidate set")

    irreversible = request.irreversible
    role = request.role or ("destination" if irreversible else "source")
    m = match(referent, cands, role=role, goal_tokens=request.goal_tokens, context=request.context)
    ranked = m.ranked
    evidence = m.evidence
    top = m.top()
    det_conf = m.confidence
    if not top:
        return ResolutionResult(
            method="abstain",
            needs_user=True,
            evidence=evidence,
            rationale="no candidate relates to the referent",
        )

    # 1) Deterministic fast path — only when the module is confident on its own.
    if is_confident(evidence, irreversible=irreversible):
        return ResolutionResult(
            chosen=str(top.get("label") or ""),
            confidence=det_conf,
            method="deterministic",
            escalated=False,
            ranked=ranked,
            evidence=evidence,
            rationale=str(top.get("why") or "deterministic name-identity match"),
        )

    # 2) Not sure enough → the module itself consults an LLM over the candidates.
    author = resolver or _default_resolver()
    labels = [c["label"] for c in cands]
    packet = {
        "referent": referent,
        "role": role,
        "candidates": [{"label": c["label"], "hints": c.get("hints") or []} for c in cands],
        "goal_tokens": list(request.goal_tokens or []),
        "context": request.context or "",
        "deterministic_suggestion": top.get("label"),
        "deterministic_evidence": evidence,
    }
    try:
        llm_payload = author.resolve(_RESOLVE_SYSTEM, packet) or {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("resolve_entity author failed: %s", exc)
        llm_payload = {}
    sanitized = _sanitize_choice(llm_payload, labels)
    llm_chosen = _clean_label(sanitized.get("chosen"))
    if llm_chosen:
        llm_conf = _top_llm_score(sanitized)
        if irreversible and llm_conf < _LLM_ACT_FLOOR:
            # The LLM ranked but stayed unsure, and a wrong send cannot be
            # undone: defer to the user rather than guess.
            return ResolutionResult(
                chosen="",
                confidence=llm_conf,
                method="abstain",
                escalated=True,
                needs_user=True,
                ranked=sanitized.get("candidates") or ranked,
                evidence=evidence,
                rationale=f"LLM unsure ({llm_conf:.2f}) under an irreversible action",
            )
        return ResolutionResult(
            chosen=llm_chosen,
            confidence=llm_conf,
            method="llm",
            escalated=True,
            ranked=sanitized.get("candidates") or ranked,
            evidence=evidence,
            rationale="semantic resolution over candidates",
        )

    # 3) The LLM produced nothing usable.
    if not irreversible:
        # A wrong open is undoable, so a reversible action may take the best
        # deterministic guess rather than bother the user.
        return ResolutionResult(
            chosen=str(top.get("label") or ""),
            confidence=det_conf,
            method="deterministic_fallback",
            escalated=True,
            ranked=ranked,
            evidence=evidence,
            rationale="LLM abstained; reversible best-effort deterministic pick",
        )
    return ResolutionResult(
        chosen="",
        confidence=det_conf,
        method="abstain",
        escalated=True,
        needs_user=True,
        ranked=ranked,
        evidence=evidence,
        rationale="no confident deterministic pick and the LLM did not resolve",
    )


# Back-compat name: single-entity resolution is the default cardinality.
resolve = resolve_one


def resolve_many(
    query: str,
    candidates: Sequence[Any],
    *,
    threshold: float = 0.0,
    top_k: Optional[int] = None,
    role: str = "",
    goal_tokens: Sequence[str] = (),
    context: str = "",
    resolver: Optional[EntityResolver] = None,
) -> MultiResolution:
    """Resolve *all* entities matching ``query`` — recall-oriented, no abstain.

    Same matcher primitive, different policy: return every candidate related to
    the query (score ≥ ``threshold``), best first, optionally capped at
    ``top_k``. Returning several — or zero — matches is expected, so there is no
    single-choice safety gate. Only when the deterministic matcher finds nothing
    does the skill consult an LLM for purely-semantic matches.

    Note: predicate filters ("idle > 1yr", "size > 1GB") belong upstream in the
    query/search step; this skill only judges semantic closeness of the set it
    is given.
    """
    referent = _clean_label(query)
    cands = _normalize_candidates(candidates)
    if not referent or not cands:
        return MultiResolution(rationale="empty referent or candidate set")

    m = match(referent, cands, role=role, goal_tokens=goal_tokens, context=context)
    ranked = m.ranked
    method = "deterministic"
    escalated = False
    rationale = "deterministic recall over candidates"

    if not ranked and resolver is not None:
        # Nothing matched lexically; a purely-semantic set may still exist.
        packet = {
            "referent": referent,
            "role": role or "source",
            "candidates": [{"label": c["label"], "hints": c.get("hints") or []} for c in cands],
            "goal_tokens": list(goal_tokens or []),
            "context": context or "",
        }
        try:
            llm_payload = resolver.resolve(_RESOLVE_SYSTEM, packet) or {}
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("resolve_many author failed: %s", exc)
            llm_payload = {}
        sanitized = _sanitize_choice(llm_payload, [c["label"] for c in cands])
        ranked = _ranked_from_llm(sanitized, cands)
        method = "llm"
        escalated = True
        rationale = "semantic recall over candidates"

    kept = [r for r in ranked if float(r.get("score") or 0.0) >= threshold]
    if top_k is not None:
        kept = kept[: max(0, int(top_k))]
    return MultiResolution(
        matches=[str(r.get("label") or "") for r in kept if r.get("label")],
        ranked=ranked,
        evidence=m.evidence,
        method=method,
        escalated=escalated,
        rationale=rationale,
    )


def resolve_texts(
    referent: str,
    candidates: Sequence[Any],
    *,
    consequence: str = "reversible",
    role: str = "",
    context: str = "",
    resolver: Optional[EntityResolver] = None,
) -> ResolutionResult:
    """Ergonomic text-in/result-out entry point for the resolution skill."""
    return resolve(
        ResolutionRequest(
            referent=referent,
            candidates=list(candidates),
            consequence=consequence,
            role=role,
            context=context,
        ),
        resolver=resolver,
    )


# How the self-contained skill's ``method`` maps onto the capability envelope's
# realization label used by the dispatcher and run logs.
_METHOD_TO_REALIZATION = {
    "deterministic": "deterministic_fast_path",
    "llm": "llm_resolver",
    "deterministic_fallback": "deterministic_after_llm",
    "abstain": "abstain_ask_user",
}


def resolve_entity(
    brief: ResolveBrief,
    resolver: Optional[EntityResolver] = None,
    *,
    use_llm: bool = False,
) -> CapabilityOutcome:
    """Capability wrapper: run the resolution skill and envelope its result.

    ``use_llm`` is retained for call-site compatibility but no longer gates
    escalation — the skill decides internally whether to consult an LLM.
    """
    labels = [_clean_label(c.get("label")) for c in brief.candidates if _clean_label(c.get("label"))]
    if not labels:
        return CapabilityOutcome(
            ok=False,
            capability="resolve_entity",
            realization="none",
            message="resolve_entity has an empty candidate_set",
            evidence={"substrate": "candidate_set", "referent": brief.referent},
        )
    if not brief.referent.strip():
        return CapabilityOutcome(
            ok=False,
            capability="resolve_entity",
            realization="none",
            message="resolve_entity needs a referent",
            evidence={"substrate": "candidate_set", "candidates": labels},
        )

    irreversible = _is_irreversible(brief.role)
    result = resolve(
        ResolutionRequest(
            referent=brief.referent,
            candidates=brief.candidates,
            consequence="irreversible" if irreversible else "reversible",
            role=brief.role,
            goal_tokens=brief.goal_tokens,
            context=brief.notes,
        ),
        resolver=resolver,
    )
    realization = _METHOD_TO_REALIZATION.get(result.method, "heuristic")
    gate = {
        "irreversible": irreversible,
        "evidence": result.evidence,
        "confidence": result.confidence,
        "method": result.method,
        "escalated": result.escalated,
    }

    if not result.chosen:
        return CapabilityOutcome(
            ok=False,
            capability="resolve_entity",
            realization=realization,
            message=(result.rationale or "resolve_entity produced no matching candidate"),
            evidence={
                "substrate": "candidate_set",
                "referent": brief.referent,
                "role": brief.role,
                "candidates": labels,
                "ranked": result.ranked,
                "resolution_gate": gate,
                "needs_user": result.needs_user,
            },
        )

    chosen = result.chosen
    chosen_meta = next(
        (c for c in brief.candidates if _clean_label(c.get("label")).lower() == chosen.lower()),
        {"label": chosen},
    )
    return CapabilityOutcome(
        ok=True,
        capability="resolve_entity",
        realization=realization,
        message=f"resolved {brief.role} referent {brief.referent!r} → {chosen!r}",
        evidence={
            "substrate": "candidate_set",
            "referent": brief.referent,
            "role": brief.role,
            "chosen": chosen,
            "confidence": result.confidence,
            "point": chosen_meta.get("point"),
            "id": chosen_meta.get("id"),
            "ranked": result.ranked,
            "candidate_labels": labels,
            "resolution_gate": gate,
        },
    )


def choose_entity_label(
    goal: Any,
    *,
    role: str = "destination",
    features: Any = None,
    world_document: Optional[Dict[str, Any]] = None,
    candidates: Optional[Sequence[Any]] = None,
    resolver: Optional[EntityResolver] = None,
) -> str:
    """Convenience for remaps: chosen label or \"\"."""
    outcome = resolve_entity(
        brief_from_context(
            goal,
            role=role,
            features=features,
            world_document=world_document,
            candidates=candidates,
        ),
        resolver=resolver,
    )
    if not outcome.ok:
        return ""
    return str(outcome.evidence.get("chosen") or "").strip()
