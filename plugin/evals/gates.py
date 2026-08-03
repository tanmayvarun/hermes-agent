"""Hard regression gates: one frozen scenario per failure we have actually seen.

Metrics move slowly and are argued about. These do not: each scenario is a
failure that reached a live run, reduced to the smallest input that reproduces
it, asserted against the code as it stands today. Any single one failing fails
CI, no averaging, no confidence interval.

The corpus holds the *recorded* versions of these failures for diagnosis; the
scenarios here are what stops them coming back. Keeping them as data rather
than as test bodies means the same list runs from the CLI report and from
pytest, and adding one is a five-line edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Sequence, Tuple


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str = ""
    question: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "question": self.question,
            "detail": self.detail[:300],
        }


@dataclass
class Gate:
    name: str
    question: str
    check: Callable[[], Tuple[bool, str]]
    # A gate for a gap we have not closed yet. It still runs and still reports,
    # but it does not fail CI -- a red suite everyone ignores protects nothing.
    known_gap: bool = False

    def run(self) -> GateResult:
        try:
            passed, detail = self.check()
        except Exception as exc:
            return GateResult(self.name, False, f"gate raised: {exc}"[:300], self.question)
        return GateResult(self.name, bool(passed), detail, self.question)


# --- the scenarios -----------------------------------------------------------


def _frontier(surface: str, ax: Sequence[Dict[str, Any]], objects: Sequence[Dict[str, Any]]):
    from plugin.agent.affordance_frontier import build_affordance_frontier
    from plugin.agent.apps.whatsapp import WhatsAppOverlay

    return build_affordance_frontier(
        surface=surface,
        goal_kind="whatsapp_forward_message",
        ax_evidence=list(ax),
        objects=list(objects),
        overlay=WhatsAppOverlay(),
    )


def _settings_is_not_a_search_affordance() -> Tuple[bool, str]:
    """A global menu item labelled Settings once became a search CTA."""
    frontier = _frontier(
        "chat_list",
        [
            {"id": 1, "role": "AXMenuItem", "label": "Settings", "bounds": [0, 0, 80, 20], "actions": ["AXPress"]},
            {"id": 2, "role": "AXSearchField", "label": "Search", "bounds": [10, 20, 200, 30], "actions": ["AXPress"]},
        ],
        [],
    )
    offenders = [
        a.id for a in frontier.observed_actions if a.target_label.strip().lower() == "settings"
    ]
    return not offenders, f"settings offered as {offenders}" if offenders else "Settings excluded as chrome"


def _generic_button_is_not_forward() -> Tuple[bool, str]:
    """Forward was once bound to whatever button happened to be nearby."""
    from plugin.agent.capabilities.resolve_entity import ResolveBrief, heuristic_resolve

    ranked = heuristic_resolve(
        ResolveBrief(
            referent="Forward",
            role="affordance",
            candidates=[{"label": "More"}, {"label": "Search"}, {"label": "Info"}],
        )
    )
    chosen = str(ranked.get("chosen") or "")
    return not chosen, f"resolved Forward to {chosen!r}" if chosen else "no candidate claimed to be Forward"


def _encryption_notice_is_not_an_object_target() -> Tuple[bool, str]:
    """A hover meant for the selected message landed on the privacy notice."""
    frontier = _frontier(
        "conversation",
        [],
        [
            {"kind": "static", "text": "Messages are end-to-end encrypted", "point": [900, 200]},
            {"kind": "message", "text": "zarooratwala.com/fresh", "point": [980, 510], "matches_goal": True},
        ],
    )
    targets = {a.target_label for a in frontier.probe_actions}
    bad = [t for t in targets if "encrypt" in t.lower()]
    if bad:
        return False, f"probe aimed at {bad}"
    return bool(targets), f"probe targets {sorted(targets)}"


def _exact_contact_beats_group_with_same_prefix() -> Tuple[bool, str]:
    """The live run opened 'Pallavi Ather Gen3' when the goal said 'Pallavi'."""
    from plugin.agent.capabilities.resolve_entity import ResolveBrief, heuristic_resolve

    ranked = heuristic_resolve(
        ResolveBrief(
            referent="Pallavi",
            role="source",
            candidates=[{"label": "Pallavi Ather Gen3"}, {"label": "Pallavi"}],
        )
    )
    chosen = str(ranked.get("chosen") or "")
    return chosen == "Pallavi", f"chose {chosen!r}"


def _self_marker_wins_for_destination() -> Tuple[bool, str]:
    """Forwarding to yourself must pick 'Tanmay (you)', not a same-named row."""
    from plugin.agent.capabilities.resolve_entity import ResolveBrief, heuristic_resolve

    ranked = heuristic_resolve(
        ResolveBrief(
            referent="Tanmay",
            role="destination",
            candidates=[{"label": "Tanmay (you)", "hints": ["self"]}, {"label": "Tanmay Kumar"}],
        )
    )
    chosen = str(ranked.get("chosen") or "")
    return chosen == "Tanmay (you)", f"chose {chosen!r}"


def _group_thread_never_wins_a_destination() -> Tuple[bool, str]:
    """Found by the corpus: the picker filtered to 'Tanmay' listed only groups.

    The recorded reply chose "Aakash <> Tanmay" at 0.8 confidence, and the
    resolver independently chose "Tanmay <> Artha". Forwarding to a group of
    strangers is the most expensive mistake on this screen.
    """
    from plugin.agent.capabilities.resolve_entity import ResolveBrief, heuristic_resolve

    ranked = heuristic_resolve(
        ResolveBrief(
            referent="Tanmay",
            role="destination",
            candidates=[
                {"label": "Tanmay <> Artha"},
                {"label": "Tanmay Saurabh Connect"},
                {"label": "Aakash <> Tanmay"},
                {"label": "Coe"},
            ],
        )
    )
    chosen = str(ranked.get("chosen") or "")
    if chosen:
        return False, f"forwarded to {chosen!r} when the person was not on screen"
    return bool(ranked.get("abstained")), "abstained with the near-misses kept for the caller"


def _containment_only_match_abstains() -> Tuple[bool, str]:
    """'Pallavi Ather Gen3' is not Pallavi, even when it is the only row."""
    from plugin.agent.capabilities.resolve_entity import ResolveBrief, heuristic_resolve

    ranked = heuristic_resolve(
        ResolveBrief(
            referent="Pallavi",
            role="source",
            candidates=[{"label": "Pallavi Ather Gen3"}, {"label": "Project management Pallavi"}],
        )
    )
    chosen = str(ranked.get("chosen") or "")
    if chosen:
        return False, f"opened {chosen!r} on containment alone"
    return len(ranked.get("candidates") or []) > 0, "abstained but kept the ranking for a retry"


def _open_source_chat_is_not_searched_again() -> Tuple[bool, str]:
    """With the source chat open, re-searching it restarts a finished phase."""
    from plugin.agent.capabilities.resolve_entity import open_matches_referent

    same = open_matches_referent("Pallavi", "Pallavi")
    other = open_matches_referent("Pallavi Ather Gen3", "Pallavi")
    if not same:
        return False, "an open chat does not match its own referent"
    if other:
        return False, "a different chat counted as the source, which locks the hunt in the wrong room"
    return True, "source match is exact, mismatch is refused"


def _picker_cannot_fall_into_sidebar_search() -> Tuple[bool, str]:
    """Typing on the forward picker once 'explained' a jump to sidebar search."""
    from plugin.agent.world_critic import critique_world_proposal

    verdict = critique_world_proposal(
        {"surface": "forward_picker", "open_conversation": "Pallavi"},
        {"surface": "search"},
        last_action="type_query",
    )
    accepted = str(verdict.surface or (verdict.accepted_document or {}).get("surface") or "")
    return accepted == "forward_picker", f"critic accepted surface {accepted!r}"


def _keyboard_open_never_overrides_a_chosen_point() -> Tuple[bool, str]:
    """Down+Return on the top hit overrode the model's own click target."""
    from plugin.agent.capabilities.resolve_entity import allow_keyboard_search_open

    with_point = allow_keyboard_search_open(
        hint="Pallavi", target_point=(285, 480), open_name="Pallavi", on_search_surface=True, search_empty=False
    )
    return not with_point, "keyboard open still fires with a point" if with_point else "point wins over keyboard"


def _blind_confident_claim_is_detected() -> Tuple[bool, str]:
    """No screenshot, no content nodes, and a conversation asserted at 0.9."""
    from plugin.evals.corpus import Fixture
    from plugin.evals.metrics import unsupported_confidence_rate

    fixture = Fixture(
        id="synthetic/blind_claim",
        phase="open_source",
        packet={
            "goal": {"operation": "whatsapp_forward_message", "source_conversation": "Pallavi"},
            "observation": {"ax_node_count": 2, "ax_content_node_count": 0, "ax_evidence": []},
        },
        response={
            "world_model": {"surface": "conversation", "open_conversation": "Pallavi"},
            "observed_state": {"surface": "conversation", "open_conversation": "Pallavi"},
            "confidence": 0.9,
        },
        screenshot={"recorded": False},
        annotation={"evidence_available": {"screenshot": False, "ax_content": False}},
    )
    result = unsupported_confidence_rate([fixture])
    return result.value == 1.0, f"detector reported {result.value}"


def _irreversible_send_is_never_a_reversible_invoke() -> Tuple[bool, str]:
    """Send buried inside invoke_affordance skips the irreversible gate."""
    from plugin.agent.capabilities.invoke_affordance import is_irreversible_affordance

    missed = [label for label in ("Send", "Delete", "Block") if not is_irreversible_affordance(label)]
    return not missed, f"treated as reversible: {missed}" if missed else "commit labels are gated"


def _latent_forward_is_never_reported_as_observed() -> Tuple[bool, str]:
    """A predicted menu item stated as fact is how an agent clicks nothing."""
    frontier = _frontier(
        "conversation",
        [],
        [{"kind": "message", "text": "zarooratwala.com/fresh", "point": [980, 510]}],
    )
    observed_labels = {a.target_label.lower() for a in frontier.observed_actions}
    if "forward" in observed_labels:
        return False, "Forward listed among observed actions while no menu is open"
    latent = [a for a in frontier.latent_actions if a.target_label.lower() == "forward"]
    if not latent:
        return False, "Forward missing from the latent set, so the probe has no motive"
    entry = latent[0]
    if entry.available_now or not entry.trigger_action:
        return False, "latent Forward is not marked as needing a trigger"
    return True, f"Forward latent behind {entry.trigger_action}"


def _sufficiency_never_acts_when_unwarranted() -> Tuple[bool, str]:
    """The dangerous error: DecisionSufficiency says "act" when it must not.

    Everything downstream is a function of this verdict, so a single false
    sufficient_to_act on the labelled corpus fails CI outright.
    """
    from plugin.evals.sufficiency import score_sufficiency_cases

    score = score_sufficiency_cases()
    if score.false_act_rate > 0.0:
        offenders = [f for f in score.failures if "sufficient=True" in f]
        return False, f"false_act_rate={score.false_act_rate}: {offenders or score.failures}"
    return True, "no labelled situation is called sufficient-to-act when it is not"


def _sufficiency_classifies_every_labelled_case() -> Tuple[bool, str]:
    """The whole labelled sufficiency corpus must classify correctly.

    The corpus *is* the spec for the computation; any flipped case is a
    regression in the executive's judgement, not a metric that may drift.
    """
    from plugin.evals.sufficiency import score_sufficiency_cases

    score = score_sufficiency_cases()
    if score.verdict_accuracy < 1.0:
        return False, f"accuracy={score.verdict_accuracy}: {score.failures}"
    if score.confidence_separation < 0.0:
        return False, f"blocked verdicts out-confidence sufficient ones ({score.confidence_separation})"
    return True, f"all {score.total} labelled sufficiency cases correct"


def _resolution_never_fast_paths_an_ambiguous_pick() -> Tuple[bool, str]:
    """The dangerous resolution error: waving an ambiguous/risky pick through.

    The fast path exists only for confident, unique, high-margin true positives.
    A single labelled case that fast-paths when it should escalate — across any
    domain — is how the agent forwards to the wrong recipient, so it fails CI.
    """
    from plugin.evals.resolution import score_resolution_cases

    score = score_resolution_cases()
    if score.false_fast_path_rate > 0.0:
        return False, f"false_fast_path_rate={score.false_fast_path_rate}: {score.failures}"
    return True, "no ambiguous/irreversible resolution is fast-pathed on the labelled set"


def _resolution_gate_transfers_across_domains() -> Tuple[bool, str]:
    """The resolution gate must classify every labelled case correctly, and the
    corpus must span multiple domains — the proof it is semantic-general rather
    than a re-specialised WhatsApp ruleset."""
    from plugin.evals.resolution import score_resolution_cases

    score = score_resolution_cases()
    if score.accuracy < 1.0:
        return False, f"accuracy={score.accuracy}: {score.failures}"
    if score.domains < 3:
        return False, f"resolution corpus only spans {score.domains} domain(s); need >=3"
    return True, f"all {score.total} resolution cases correct across {score.domains} domains"


def _goal_keyword_in_a_filename_is_not_an_object() -> Tuple[bool, str]:
    """A run log named ...zarooratwala.jsonl once entered the active graph."""
    frontier = _frontier(
        "conversation",
        [
            {
                "id": 5,
                "role": "AXStaticText",
                "label": "forward_zarooratwala_live_20260802.jsonl",
                "bounds": [0, 0, 200, 12],
                "actions": [],
            }
        ],
        [],
    )
    named = [a.target_label for a in frontier.observed_actions if "jsonl" in a.target_label.lower()]
    return not named, f"filename entered the frontier as {named}" if named else "filename is not actionable"


GATES: Tuple[Gate, ...] = (
    Gate(
        "settings_is_not_a_search_affordance",
        "Does a global menu item become a task CTA?",
        _settings_is_not_a_search_affordance,
    ),
    Gate(
        "generic_button_is_not_forward",
        "Does an unrelated button get bound to Forward?",
        _generic_button_is_not_forward,
    ),
    Gate(
        "encryption_notice_is_not_an_object_target",
        "Does an object-scoped gesture stay on the object?",
        _encryption_notice_is_not_an_object_target,
    ),
    Gate(
        "exact_contact_beats_group_with_same_prefix",
        "Does 'Pallavi' open Pallavi rather than a group starting with it?",
        _exact_contact_beats_group_with_same_prefix,
    ),
    Gate(
        "self_marker_wins_for_destination",
        "Does forwarding to yourself resolve the (you) row?",
        _self_marker_wins_for_destination,
    ),
    Gate(
        "group_thread_never_wins_a_destination",
        "Can a group chat receive a message meant for a person?",
        _group_thread_never_wins_a_destination,
    ),
    Gate(
        "containment_only_match_abstains",
        "Does a name that merely contains the referent get acted on?",
        _containment_only_match_abstains,
    ),
    Gate(
        "open_source_chat_is_not_searched_again",
        "Is a finished phase ever restarted?",
        _open_source_chat_is_not_searched_again,
    ),
    Gate(
        "picker_cannot_fall_into_sidebar_search",
        "Can a picker jump to sidebar search on a typing action?",
        _picker_cannot_fall_into_sidebar_search,
    ),
    Gate(
        "keyboard_open_never_overrides_a_chosen_point",
        "Does a keyboard shortcut override a chosen target?",
        _keyboard_open_never_overrides_a_chosen_point,
    ),
    Gate(
        "blind_confident_claim_is_detected",
        "Would a confident claim with no evidence be caught?",
        _blind_confident_claim_is_detected,
    ),
    Gate(
        "irreversible_send_is_never_a_reversible_invoke",
        "Can Send be taken through the reversible path?",
        _irreversible_send_is_never_a_reversible_invoke,
    ),
    Gate(
        "latent_forward_is_never_reported_as_observed",
        "Is a predicted control ever stated as present?",
        _latent_forward_is_never_reported_as_observed,
    ),
    Gate(
        "goal_keyword_in_a_filename_is_not_an_object",
        "Does lexical similarity beat structural eligibility?",
        _goal_keyword_in_a_filename_is_not_an_object,
    ),
    Gate(
        "sufficiency_never_acts_when_unwarranted",
        "Does the brain ever call it sufficient-to-act when it is not?",
        _sufficiency_never_acts_when_unwarranted,
    ),
    Gate(
        "resolution_never_fast_paths_an_ambiguous_pick",
        "Does an ambiguous/irreversible referent ever skip semantic resolution?",
        _resolution_never_fast_paths_an_ambiguous_pick,
    ),
    Gate(
        "resolution_gate_transfers_across_domains",
        "Does the resolution gate classify correctly across chat/files/tabs?",
        _resolution_gate_transfers_across_domains,
    ),
    Gate(
        "sufficiency_classifies_every_labelled_case",
        "Does the sufficiency computation match its labelled spec?",
        _sufficiency_classifies_every_labelled_case,
    ),
)


def run_gates(gates: Sequence[Gate] = GATES) -> List[GateResult]:
    return [gate.run() for gate in gates]


def blocking_failures(results: Sequence[GateResult], gates: Sequence[Gate] = GATES) -> List[GateResult]:
    """Failures that must fail CI, excluding gaps we have declared open."""
    known = {gate.name for gate in gates if gate.known_gap}
    return [r for r in results if not r.passed and r.name not in known]


# --- statistical gates -------------------------------------------------------


@dataclass
class StatGate:
    """A metric that may drift, but only so far, and only in one direction."""

    metric: str
    max_drop: float = 0.0
    max_rise: float = 0.0
    note: str = ""


STAT_GATES: Tuple[StatGate, ...] = (
    StatGate("critical_cta_recall", max_drop=0.01, note="a missing CTA is a task the agent cannot do"),
    StatGate("top3_acceptable_action_rate", max_drop=0.02),
    StatGate("surface_accuracy", max_drop=0.02),
    StatGate("target_grounding_accuracy", max_drop=0.02),
    StatGate("chrome_pollution_rate", max_rise=0.05),
    StatGate("invalid_cta_rate", max_rise=0.02),
    StatGate("forbidden_action_rate", max_rise=0.02),
    StatGate("unsupported_high_confidence_rate", max_rise=0.01, note="never let this drift up"),
)


def compare_to_baseline(
    current: Dict[str, Any], baseline: Dict[str, Any], gates: Sequence[StatGate] = STAT_GATES
) -> List[Dict[str, Any]]:
    """Which metrics moved further than their gate allows."""
    now = {m["name"]: m for m in (current.get("metrics") or [])}
    before = {m["name"]: m for m in (baseline.get("metrics") or [])}
    breaches: List[Dict[str, Any]] = []
    for gate in gates:
        new = now.get(gate.metric, {}).get("value")
        old = before.get(gate.metric, {}).get("value")
        if new is None or old is None:
            continue
        delta = float(new) - float(old)
        if gate.max_drop and delta < -gate.max_drop:
            breaches.append(
                {"metric": gate.metric, "before": old, "after": new, "delta": round(delta, 4), "limit": -gate.max_drop}
            )
        if gate.max_rise and delta > gate.max_rise:
            breaches.append(
                {"metric": gate.metric, "before": old, "after": new, "delta": round(delta, 4), "limit": gate.max_rise}
            )
    return breaches


# --- temporal-consistency gates ---------------------------------------------
# The temporal layer used to be purely informational. These give it teeth: a run
# that starts flip-flopping beliefs or sliding phases backward more than the
# baseline allowed is a regression, not a curiosity. The temporal summary is a
# flat dict (not the {name, value} metric list), so it gets its own comparison.

TEMPORAL_STAT_GATES: Tuple[StatGate, ...] = (
    StatGate("belief_flip_rate", max_rise=0.05, note="beliefs that revert A->B->A are incoherence"),
    StatGate("unjustified_phase_regression_rate", max_rise=0.02, note="phase slid back with no screen change"),
    StatGate("surface_stability", max_drop=0.05, note="oscillating surfaces are a lost world model"),
    StatGate("object_identity_continuity", max_drop=0.05, note="an id that renames is a dropped object"),
)


def compare_temporal_to_baseline(
    current: Dict[str, Any],
    baseline: Dict[str, Any],
    gates: Sequence[StatGate] = TEMPORAL_STAT_GATES,
) -> List[Dict[str, Any]]:
    """Which temporal metrics regressed past their gate against the baseline."""
    breaches: List[Dict[str, Any]] = []
    for gate in gates:
        new = current.get(gate.metric)
        old = baseline.get(gate.metric)
        if new is None or old is None:
            continue
        delta = float(new) - float(old)
        if gate.max_drop and delta < -gate.max_drop:
            breaches.append(
                {"metric": gate.metric, "before": old, "after": new, "delta": round(delta, 4), "limit": -gate.max_drop}
            )
        if gate.max_rise and delta > gate.max_rise:
            breaches.append(
                {"metric": gate.metric, "before": old, "after": new, "delta": round(delta, 4), "limit": gate.max_rise}
            )
    return breaches
