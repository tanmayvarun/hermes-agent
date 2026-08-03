"""The ten priority metrics, one layer at a time.

Three separate truths, never collapsed into one score:

    Did the system see the world correctly?      sensing, structure
    Did it understand what could be done?        affordance, latent affordance
    Did it choose a useful next action?          relevance, ranking

Each metric returns its value *and* the number of fixtures it could actually
score. A metric that silently skipped 80% of the corpus and reported 0.95 is
worse than no metric, so ``scored`` and ``skipped`` travel with every value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from plugin.evals.annotations import (
    CHROME_LABELS,
    CHROME_NOTICES,
    is_chrome_node,
    label_matches,
    normalize_family,
)
from plugin.evals.corpus import Fixture, model_surface

LAYER_OBSERVATION = "observation"
LAYER_STRUCTURE = "structure"
LAYER_AFFORDANCE = "affordance"
LAYER_LATENT = "latent_affordance"
LAYER_RELEVANCE = "relevance"
LAYER_RANKING = "ranking"
LAYER_UNCERTAINTY = "uncertainty"
LAYER_END_TO_END = "end_to_end"


@dataclass
class MetricResult:
    name: str
    layer: str
    value: Optional[float]
    scored: int = 0
    skipped: int = 0
    question: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)
    # Whether a higher number is better. Pollution and invalid-CTA rates are
    # metrics you want to fall, and a report that does not know that will
    # cheerfully celebrate a regression.
    higher_is_better: bool = True
    examples: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "layer": self.layer,
            "value": None if self.value is None else round(float(self.value), 4),
            "scored": self.scored,
            "skipped": self.skipped,
            "question": self.question,
            "higher_is_better": self.higher_is_better,
            "detail": self.detail,
            "examples": self.examples[:5],
        }


def _rate(hits: float, total: float) -> Optional[float]:
    return None if total <= 0 else hits / total


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


# --- layer: observation ------------------------------------------------------


def ax_content_recall(fixtures: Sequence[Fixture]) -> MetricResult:
    """Did the controls the phase needs survive extraction?

    Weighted, because a critical CTA and a decorative label are not worth the
    same: dropping the search field fails the task no matter how many static
    strings came through with it.
    """
    weighted_found = 0.0
    weighted_needed = 0.0
    scored = 0
    skipped = 0
    misses: List[str] = []
    for fixture in fixtures:
        required = (fixture.annotation or {}).get("required_controls") or []
        if not required:
            skipped += 1
            continue
        scored += 1
        nodes = fixture.ax_evidence
        for want in required:
            weight = float(want.get("weight") or 1)
            weighted_needed += weight
            wanted_label = str(want.get("label") or "")
            kind = str(want.get("kind") or "")
            found = False
            for node in nodes:
                if is_chrome_node(node):
                    continue
                if wanted_label and label_matches(str(node.get("label") or ""), wanted_label):
                    found = True
                    break
                if not wanted_label and _kind_matches(kind, node):
                    found = True
                    break
            if found:
                weighted_found += weight
            elif len(misses) < 12:
                misses.append(f"{fixture.id}: no {kind} {wanted_label}".strip())
    return MetricResult(
        name="ax_content_recall",
        layer=LAYER_OBSERVATION,
        value=_rate(weighted_found, weighted_needed),
        scored=scored,
        skipped=skipped,
        question="Did required evidence survive sensing?",
        detail={"weighted_found": weighted_found, "weighted_required": weighted_needed},
        examples=misses,
    )


def _kind_matches(kind: str, node: Dict[str, Any]) -> bool:
    role = _norm(node.get("role"))
    table = {
        "search_input": {"axtextfield", "axsearchfield", "axtextarea"},
        "conversation_row": {"axrow", "axcell", "axoutlinerow"},
        "message": {"axstatictext", "axgroup"},
        "menu_item": {"axmenuitem"},
        "destination_row": {"axrow", "axcell"},
        "destination_filter": {"axtextfield", "axsearchfield"},
        "timeline": {"axscrollarea", "axtable", "axlist"},
    }
    return role in table.get(kind, set())


def chrome_pollution_rate(fixtures: Sequence[Fixture]) -> MetricResult:
    """How much of what survived sensing is application shell.

    The failure this measures is the one that swung both ways: a traversal
    broad enough to attach menu-bar items to messages, then narrow enough to
    drop the content entirely.
    """
    polluted = 0
    total = 0
    scored = 0
    worst: List[str] = []
    for fixture in fixtures:
        nodes = fixture.ax_evidence
        if not nodes:
            continue
        scored += 1
        chrome = sum(1 for node in nodes if is_chrome_node(node))
        polluted += chrome
        total += len(nodes)
        if chrome == len(nodes) and len(worst) < 12:
            worst.append(f"{fixture.id}: all {len(nodes)} retained nodes are chrome")
    return MetricResult(
        name="chrome_pollution_rate",
        layer=LAYER_OBSERVATION,
        value=_rate(polluted, total),
        scored=scored,
        skipped=len(fixtures) - scored,
        question="How much of the retained tree is irrelevant?",
        detail={"chrome_nodes": polluted, "retained_nodes": total},
        higher_is_better=False,
        examples=worst,
    )


# --- layer: structure --------------------------------------------------------


def _gold_surface(fixture: Fixture) -> str:
    """The surface only when a human confirmed it against the screenshot."""
    annotation = fixture.annotation or {}
    if (annotation.get("sources") or {}).get("surface") != "manual":
        return ""
    return _norm(annotation.get("surface"))


def surface_accuracy(fixtures: Sequence[Fixture]) -> MetricResult:
    """Did the system name the screen it was actually looking at?

    Scored against gold labels only. The AX-derived label reports the base
    pane, so an overlay the model correctly reported would be counted wrong --
    the metric would punish the behaviour it exists to protect. Agreement with
    the derived label is reported separately, as the weaker thing it is.
    """
    hits = 0
    scored = 0
    skipped = 0
    wrong: List[str] = []
    confusion: Dict[str, int] = {}
    for fixture in fixtures:
        truth = _gold_surface(fixture)
        if not truth:
            skipped += 1
            continue
        scored += 1
        got = model_surface(fixture)
        if got == truth:
            hits += 1
        else:
            confusion[f"{truth}->{got or 'none'}"] = confusion.get(f"{truth}->{got or 'none'}", 0) + 1
            if len(wrong) < 12:
                wrong.append(f"{fixture.id}: truth={truth} model={got or 'none'}")
    return MetricResult(
        name="surface_accuracy",
        layer=LAYER_STRUCTURE,
        value=_rate(hits, scored),
        scored=scored,
        skipped=skipped,
        question="Did objects and regions form the correct hierarchy?",
        detail={
            "confusions": dict(sorted(confusion.items(), key=lambda kv: -kv[1])),
            "gold_labels": scored,
        },
        examples=wrong,
    )


def surface_agreement_with_shadow(fixtures: Sequence[Fixture]) -> MetricResult:
    """How often the reply matches the AX-derived screen label.

    A diagnostic, not a score. The two disagree most where the model is right
    -- an open overlay the base label cannot see -- so a fall here is a prompt
    to look at frames, not evidence of a regression. It is worth tracking
    because a sudden jump either way means one of the two readings changed.
    """
    agree = 0
    scored = 0
    drift: List[str] = []
    for fixture in fixtures:
        annotation = fixture.annotation or {}
        if (annotation.get("sources") or {}).get("surface") not in {"shadow", "shadow_fused"}:
            continue
        truth = _norm(annotation.get("surface"))
        if not truth:
            continue
        scored += 1
        got = model_surface(fixture)
        if got == truth:
            agree += 1
        elif len(drift) < 12:
            drift.append(f"{fixture.id}: ax={truth} model={got or 'none'}")
    return MetricResult(
        name="surface_agreement_with_shadow",
        layer=LAYER_STRUCTURE,
        value=_rate(agree, scored),
        scored=scored,
        skipped=len(fixtures) - scored,
        question="Do the two independent readings of the screen agree?",
        examples=drift,
    )


def overlay_detection(fixtures: Sequence[Fixture]) -> MetricResult:
    """When something is layered over the app, is it reported?

    A context menu or a send-to sheet owns the interaction while it is open.
    Missing it means proposing actions against a pane the user cannot reach.
    """
    hits = 0
    scored = 0
    missed: List[str] = []
    for fixture in fixtures:
        state = (fixture.annotation or {}).get("surface_state") or {}
        overlay = _norm(state.get("overlay"))
        if not overlay or overlay == "none":
            continue
        scored += 1
        if model_surface(fixture) == overlay:
            hits += 1
        elif len(missed) < 12:
            missed.append(f"{fixture.id}: {overlay} open, model said {model_surface(fixture) or 'none'}")
    return MetricResult(
        name="overlay_detection_rate",
        layer=LAYER_STRUCTURE,
        value=_rate(hits, scored),
        scored=scored,
        skipped=len(fixtures) - scored,
        question="Is a surface layered over the app noticed?",
        examples=missed,
    )


def target_grounding_accuracy(fixtures: Sequence[Fixture]) -> MetricResult:
    """When the goal object is on screen, does the action point at it?

    Object-scope preservation is the specific failure: the model says act on
    the selected message and the runtime binds the gesture to the
    end-to-end-encryption notice sitting near it.
    """
    hits = 0
    scored = 0
    skipped = 0
    drift: List[str] = []
    for fixture in fixtures:
        target = (fixture.annotation or {}).get("target_object")
        action = fixture.next_action
        if not target or not action:
            skipped += 1
            continue
        family = _norm(action.get("family"))
        if family not in _OBJECT_SCOPED:
            skipped += 1
            continue
        scored += 1
        wanted = str(target.get("text") or "")
        named = str(action.get("target_label") or action.get("text") or "")
        by_id = action.get("target_id") not in (None, "") and action.get("target_id") == target.get("ax_id")
        if by_id or label_matches(named, wanted):
            hits += 1
        elif len(drift) < 12:
            drift.append(f"{fixture.id}: wanted {wanted!r} got {named or action.get('target_id')!r}")
    return MetricResult(
        name="target_grounding_accuracy",
        layer=LAYER_STRUCTURE,
        value=_rate(hits, scored),
        scored=scored,
        skipped=skipped,
        question="Did the action attach to the object the goal is about?",
        examples=drift,
    )


_OBJECT_SCOPED = {
    "click",
    "right_click",
    "hover",
    "select_content",
    "reveal_actions",
    "open_entity",
    "open_contact",
    "resolve_entity",
    "invoke_affordance",
}


# --- layer: affordance -------------------------------------------------------


def _frontier_for(fixture: Fixture):
    from plugin.agent.affordance_frontier import build_affordance_frontier
    from plugin.agent.apps.registry import get_overlay

    surface = _norm((fixture.annotation or {}).get("surface")) or model_surface(fixture)
    try:
        overlay = get_overlay(str(fixture.observation.get("app") or ""), None)
    except Exception:
        overlay = None
    return build_affordance_frontier(
        surface=surface,
        goal_kind=str(fixture.goal.get("operation") or ""),
        ax_evidence=fixture.ax_evidence,
        objects=fixture.objects,
        overlay=overlay,
    )


def critical_cta_recall(fixtures: Sequence[Fixture]) -> MetricResult:
    """Does the frontier offer what the phase actually needs?

    Recall matters more than precision here: a missing critical CTA means the
    model has to invent the move from pixels, which is the situation this whole
    layer exists to remove.
    """
    found = 0
    needed = 0
    scored = 0
    gaps: List[str] = []
    for fixture in fixtures:
        critical = list((fixture.annotation or {}).get("critical_ctas") or [])
        if not critical:
            continue
        scored += 1
        frontier = _frontier_for(fixture)
        offered = {a.family for a in frontier.observed_actions} | {
            a.family for a in frontier.probe_actions
        }
        reachable = {e.from_action for e in frontier.known_transition_edges}
        for family in critical:
            needed += 1
            if family in offered or family in reachable:
                found += 1
            elif len(gaps) < 12:
                gaps.append(f"{fixture.id}: frontier omits {family}")
    return MetricResult(
        name="critical_cta_recall",
        layer=LAYER_AFFORDANCE,
        value=_rate(found, needed),
        scored=scored,
        skipped=len(fixtures) - scored,
        question="Did it identify what can be done now?",
        detail={"critical_found": found, "critical_required": needed},
        examples=gaps,
    )


def invalid_cta_rate(fixtures: Sequence[Fixture]) -> MetricResult:
    """How often the frontier offers something the phase forbids.

    False affordances are worse than missing ones because they create branches
    the runtime will actually walk down.
    """
    invalid = 0
    total = 0
    scored = 0
    offences: List[str] = []
    for fixture in fixtures:
        annotation = fixture.annotation or {}
        forbidden = set(annotation.get("forbidden_next_actions") or [])
        if not forbidden:
            continue
        scored += 1
        frontier = _frontier_for(fixture)
        for affordance in frontier.observed_actions:
            total += 1
            if affordance.family in forbidden:
                invalid += 1
                if len(offences) < 12:
                    offences.append(
                        f"{fixture.id}: offers {affordance.family} ({affordance.target_label})"
                    )
    return MetricResult(
        name="invalid_cta_rate",
        layer=LAYER_AFFORDANCE,
        value=_rate(invalid, total),
        scored=scored,
        skipped=len(fixtures) - scored,
        question="Did it invent actions the surface does not support?",
        detail={"invalid": invalid, "offered": total},
        higher_is_better=False,
        examples=offences,
    )


def latent_affordance_pr(fixtures: Sequence[Fixture]) -> MetricResult:
    """Precision and recall over what a probe is predicted to reveal.

    Scored as F1 so one number can move the report, with both halves kept in
    the detail: recall alone rewards predicting every menu item in existence,
    precision alone rewards predicting nothing.
    """
    tp = fp = fn = 0
    scored = 0
    fantasies: List[str] = []
    for fixture in fixtures:
        annotation = fixture.annotation or {}
        wanted = {_norm(x) for x in (annotation.get("latent_affordances") or [])}
        # An empty *gold* set is a real label -- on an open context menu the
        # actions are observed, so any latent prediction there is invention.
        manual = (annotation.get("sources") or {}).get("latent_affordances") == "manual"
        if not wanted and not manual:
            continue
        scored += 1
        frontier = _frontier_for(fixture)
        got = {_norm(a.target_label) for a in frontier.latent_actions}
        got |= {_norm(m.label) for p in frontier.probe_actions for m in p.may_reveal}
        tp += len(wanted & got)
        missing = wanted - got
        extra = got - wanted
        fn += len(missing)
        fp += len(extra)
        for label in sorted(extra)[:2]:
            if len(fantasies) < 12:
                fantasies.append(f"{fixture.id}: predicted {label!r} which is not in ground truth")
    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)
    f1 = None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)
    return MetricResult(
        name="latent_affordance_f1",
        layer=LAYER_LATENT,
        value=f1,
        scored=scored,
        skipped=len(fixtures) - scored,
        question="Did it predict what probes may reveal?",
        detail={
            "precision": None if precision is None else round(precision, 4),
            "recall": None if recall is None else round(recall, 4),
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
        },
        examples=fantasies,
    )


# --- layer: relevance and ranking -------------------------------------------


def task_focus_score(fixtures: Sequence[Fixture]) -> MetricResult:
    """Did attention stay on the task-relevant subgraph?

    A system can enumerate every CTA correctly and still fail by acting on the
    wrong one. Objects the model reported are credited when they relate to the
    goal and penalised when they are shell chrome.
    """
    credit = 0.0
    possible = 0.0
    scored = 0
    distracted: List[str] = []
    for fixture in fixtures:
        objects = fixture.objects
        if not objects:
            continue
        scored += 1
        terms = [
            _norm(fixture.goal.get(key))
            for key in ("source_conversation", "source_query", "destination")
        ]
        terms = [t for t in terms if t]
        for item in objects:
            text = _norm(item.get("text"))
            possible += 1
            if any(term in text for term in terms):
                credit += 1
            elif _is_chrome_text(text):
                credit -= 1
                if len(distracted) < 12:
                    distracted.append(f"{fixture.id}: chrome object {text!r} in the active graph")
    return MetricResult(
        name="task_focus_score",
        layer=LAYER_RELEVANCE,
        value=_rate(credit, possible),
        scored=scored,
        skipped=len(fixtures) - scored,
        question="Did it focus on the task-relevant subgraph?",
        detail={"credited": credit, "objects": possible},
        examples=distracted,
    )


def distractor_capture_rate(fixtures: Sequence[Fixture]) -> MetricResult:
    """Did lexical similarity beat structural eligibility?

    The picker filtered to "Tanmay" lists a dozen groups whose names contain
    it and not the person. Choosing one of those is not a near miss; it sends
    the message to strangers.
    """
    captured = 0
    scored = 0
    caught: List[str] = []
    for fixture in fixtures:
        traps = [str(d) for d in ((fixture.annotation or {}).get("distractors") or [])]
        action = fixture.next_action
        if not traps or not action:
            continue
        scored += 1
        named = _norm(action.get("target_label") or action.get("text"))
        if named and any(_norm(trap) == named for trap in traps):
            captured += 1
            if len(caught) < 12:
                caught.append(f"{fixture.id}: chose the distractor {named!r}")
    return MetricResult(
        name="distractor_capture_rate",
        layer=LAYER_RELEVANCE,
        value=_rate(captured, scored),
        scored=scored,
        skipped=len(fixtures) - scored,
        question="Does a similar name beat the right one?",
        higher_is_better=False,
        examples=caught,
    )


def _is_chrome_text(text: str) -> bool:
    low = _norm(text)
    if any(low == term or low.startswith(term + " ") for term in CHROME_LABELS):
        return True
    return any(notice in low for notice in CHROME_NOTICES)


def object_scope_violations(fixtures: Sequence[Fixture]) -> MetricResult:
    """Object-scoped gestures aimed at application chrome.

    Scoreable without any ground truth about where the real target is: a hover
    meant for a message can never correctly land on the encryption notice, and
    that is the exact shape of the bug this catches.
    """
    bad = 0
    scored = 0
    offences: List[str] = []
    for fixture in fixtures:
        action = fixture.next_action
        if not action or _norm(action.get("family")) not in _OBJECT_SCOPED:
            continue
        scored += 1
        named = str(action.get("target_label") or action.get("text") or "")
        if named and _is_chrome_text(named):
            bad += 1
            if len(offences) < 12:
                offences.append(f"{fixture.id}: {action.get('family')} aimed at {named!r}")
    return MetricResult(
        name="object_scope_violation_rate",
        layer=LAYER_STRUCTURE,
        value=_rate(bad, scored),
        scored=scored,
        skipped=len(fixtures) - scored,
        question="Do object-scoped gestures stay on task objects?",
        higher_is_better=False,
        examples=offences,
    )


def top_k_acceptable(fixtures: Sequence[Fixture], k: int = 3) -> MetricResult:
    """Is a useful move among the top k, and how high is the best one?

    Top-1 alone punishes a model that offered the right move second when the
    first was merely inadmissible -- which the runtime now recovers from -- so
    the reciprocal rank travels alongside.
    """
    hits = 0
    scored = 0
    reciprocal = 0.0
    ranked_frames = 0
    misses: List[str] = []
    for fixture in fixtures:
        annotation = fixture.annotation or {}
        acceptable = {k2: v for k2, v in (annotation.get("acceptable_next_actions") or {}).items() if v > 0}
        if not acceptable:
            continue
        candidates = fixture.next_actions
        if not candidates:
            continue
        scored += 1
        if len(candidates) > 1:
            ranked_frames += 1
        surface = str(annotation.get("surface") or model_surface(fixture))
        rank = 0
        for index, action in enumerate(candidates[:k]):
            if normalize_family(str(action.get("family")), surface) in acceptable:
                rank = index + 1
                break
        if rank:
            hits += 1
            reciprocal += 1.0 / rank
        elif len(misses) < 12:
            families = [str(a.get("family")) for a in candidates[:k]]
            misses.append(f"{fixture.id}: proposed {families} on {surface}, none acceptable")
    return MetricResult(
        name=f"top{k}_acceptable_action_rate",
        layer=LAYER_RANKING,
        value=_rate(hits, scored),
        scored=scored,
        skipped=len(fixtures) - scored,
        question="Are useful actions high in the frontier?",
        detail={
            "mean_reciprocal_rank": round(reciprocal / scored, 4) if scored else None,
            "frames_with_ranked_frontier": ranked_frames,
            # A corpus recorded before the ranked contract has one action per
            # frame, so top-3 equals top-1 until this rises.
            "ranked_frontier_coverage": round(ranked_frames / scored, 4) if scored else None,
        },
        examples=misses,
    )


def forbidden_action_rate(fixtures: Sequence[Fixture]) -> MetricResult:
    """How often the chosen move is one the surface forbids."""
    bad = 0
    scored = 0
    offences: List[str] = []
    for fixture in fixtures:
        forbidden = set((fixture.annotation or {}).get("forbidden_next_actions") or [])
        action = fixture.next_action
        if not forbidden or not action:
            continue
        scored += 1
        surface = str((fixture.annotation or {}).get("surface") or model_surface(fixture))
        family = normalize_family(str(action.get("family")), surface)
        if family in forbidden:
            bad += 1
            if len(offences) < 12:
                offences.append(f"{fixture.id}: {family} on {surface}")
    return MetricResult(
        name="forbidden_action_rate",
        layer=LAYER_RANKING,
        value=_rate(bad, scored),
        scored=scored,
        skipped=len(fixtures) - scored,
        question="Did it pick a move this surface forbids?",
        higher_is_better=False,
        examples=offences,
    )


# --- layer: uncertainty ------------------------------------------------------


def unsupported_confidence_rate(fixtures: Sequence[Fixture], *, floor: float = 0.7) -> MetricResult:
    """Confident claims the evidence could not support.

    The dangerous failure is not being wrong; it is being wrong at 0.9 with no
    screenshot and no content nodes, because everything downstream treats that
    as settled.
    """
    unsupported = 0
    scored = 0
    claims: List[str] = []
    for fixture in fixtures:
        if not fixture.response:
            continue
        evidence = (fixture.annotation or {}).get("evidence_available") or {}
        scored += 1
        blind = not evidence.get("screenshot") and not evidence.get("ax_content")
        state = (fixture.response or {}).get("observed_state") or {}
        document = fixture.document
        asserted = bool(
            str(state.get("open_conversation") or document.get("open_conversation") or "").strip()
            or state.get("target_object_visible")
            or document.get("objects")
        )
        if blind and asserted and fixture.confidence >= floor:
            unsupported += 1
            if len(claims) < 12:
                claims.append(
                    f"{fixture.id}: confidence {fixture.confidence} with no screenshot and no AX content"
                )
            continue
        for belief in document.get("beliefs") or []:
            if not isinstance(belief, dict):
                continue
            try:
                strength = float(belief.get("confidence") or 0.0)
            except (TypeError, ValueError):
                strength = 0.0
            if strength >= floor and not (belief.get("evidence") or []):
                unsupported += 1
                if len(claims) < 12:
                    claims.append(f"{fixture.id}: belief {belief.get('predicate')!r} asserted without evidence")
                break
    return MetricResult(
        name="unsupported_high_confidence_rate",
        layer=LAYER_UNCERTAINTY,
        value=_rate(unsupported, scored),
        scored=scored,
        skipped=len(fixtures) - scored,
        question="Does it know when it does not know?",
        higher_is_better=False,
        examples=claims,
    )


def evidence_gap_honesty(fixtures: Sequence[Fixture]) -> MetricResult:
    """When the perceptor could not establish something, did it say so?

    Incompleteness is the normal operating condition, so the useful contract is
    not "return a complete world" but "return what you established and name
    what you did not". A blind frame answered without a single declared gap is
    the failure this measures -- the executive has no way to know it should
    gather more evidence before acting.
    """
    honest = 0
    scored = 0
    silent: List[str] = []
    for fixture in fixtures:
        if not fixture.response:
            continue
        evidence = (fixture.annotation or {}).get("evidence_available") or {}
        thin = not evidence.get("ax_content")
        if not thin:
            continue
        scored += 1
        response = fixture.response or {}
        gaps = (
            (response.get("missing_evidence") or [])
            + (response.get("evidence_gaps") or [])
            + (response.get("missing_affordance_information") or [])
        )
        if gaps:
            honest += 1
        elif len(silent) < 12:
            silent.append(f"{fixture.id}: no AX content, no declared gap, confidence {fixture.confidence}")
    return MetricResult(
        name="evidence_gap_declaration_rate",
        layer=LAYER_UNCERTAINTY,
        value=_rate(honest, scored),
        scored=scored,
        skipped=len(fixtures) - scored,
        question="Does it name what it could not establish?",
        examples=silent,
    )


ALL_METRICS = (
    ax_content_recall,
    chrome_pollution_rate,
    surface_accuracy,
    surface_agreement_with_shadow,
    overlay_detection,
    target_grounding_accuracy,
    object_scope_violations,
    critical_cta_recall,
    invalid_cta_rate,
    latent_affordance_pr,
    task_focus_score,
    distractor_capture_rate,
    top_k_acceptable,
    forbidden_action_rate,
    unsupported_confidence_rate,
    evidence_gap_honesty,
)


def evaluate_all(fixtures: Sequence[Fixture]) -> List[MetricResult]:
    results: List[MetricResult] = []
    for metric in ALL_METRICS:
        try:
            results.append(metric(fixtures))
        except Exception as exc:  # a broken metric must not hide the others
            results.append(
                MetricResult(
                    name=getattr(metric, "__name__", "metric"),
                    layer="error",
                    value=None,
                    question=f"failed: {exc}"[:160],
                )
            )
    return results
