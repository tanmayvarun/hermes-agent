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


def _golden_known_gap_ids() -> set:
    """Case ids declared open debt in the manifest — do not block CI."""
    from plugin.evals.golden.schema import load_manifest

    manifest = load_manifest() or {}
    gaps = manifest.get("known_gap_case_ids") or []
    return {str(x).strip() for x in gaps if str(x).strip()}


def _golden_v1_modules_pass() -> Tuple[bool, str]:
    """Every non-gap golden case must pass — failure names the case + layer.

    ``known_gap_case_ids`` in the corpus manifest are explicit open debt; they
    still appear in the score report but do not red the gate. New failures
    outside that list always block.
    """
    from plugin.evals.golden.score import score_all

    report = score_all()
    modules = report.get("modules") or {}
    gaps = _golden_known_gap_ids()
    fails: List[str] = []
    gap_hits: List[str] = []
    for name, block in modules.items():
        for f in block.get("failures") or []:
            cid = str(f.get("case_id") or "")
            if cid in gaps:
                gap_hits.append(cid)
                continue
            bad_checks = [
                c.get("name")
                for c in (f.get("checks") or [])
                if isinstance(c, dict) and not c.get("passed")
            ][:4]
            fails.append(f"{cid}:{bad_checks}")
    if fails:
        return False, "; ".join(fails[:8])
    n = report.get("cases_total")
    mean = report.get("mean_accuracy")
    gap_note = f" known_gaps={len(gap_hits)}" if gap_hits else ""
    return True, f"mean={mean} cases={n}{gap_note}"


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


def _text_compose_author_never_uses_vision_task() -> Tuple[bool, str]:
    """032207: compose_search_query froze on qwen3.5:cloud via task=perception.

    Text-only query authorship must resolve onto the decision/inference stack
    even when the caller (or a legacy default) still says ``perception`` and
    the launcher has pinned perception to a vision SoT.
    """
    from plugin.agent.consultation_routing import (
        is_vision_task,
        resolve_reasoning_route,
    )

    text_msgs = [
        {"role": "system", "content": "You author search-box queries."},
        {"role": "user", "content": "Author the next search-box query."},
    ]
    route = resolve_reasoning_route(
        "perception",
        text_msgs,
        usecase="compose_search_query",
    )
    if is_vision_task(route.task):
        return False, f"compose author still on vision task={route.task}"
    if route.task != "decision":
        return False, f"expected decision, got {route.task} reason={route.reason}"
    if "text_messages_must_not_use_vision_task" not in route.constraints:
        return False, f"missing constraint; constraints={route.constraints}"
    # Multimodal must still land on perception.
    vision_msgs = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "read"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}},
            ],
        }
    ]
    mm = resolve_reasoning_route("decision", vision_msgs, usecase="perception")
    if not is_vision_task(mm.task):
        return False, f"multimodal failed to upgrade: task={mm.task}"
    return True, f"text→{route.task}; multimodal→{mm.task}"


def _meta_packet_shaped_from_live_situations() -> Tuple[bool, str]:
    """LLM meta packet must carry mined sections; corpus must include live sits."""
    from plugin.agent.executive.meta_action import MetaContext
    from plugin.agent.executive.meta_consultation import meta_context_packet
    from plugin.agent.executive.meta_situation import META_PACKET_REQUIRED_SECTIONS
    from plugin.evals.golden.schema import load_module_cases

    packet = meta_context_packet(MetaContext(has_grounded_action=True))
    missing = [s for s in META_PACKET_REQUIRED_SECTIONS if s not in packet]
    if missing:
        return False, f"packet missing sections {missing}"
    cases = load_module_cases("meta_action")
    mined = [c for c in cases if "mined_live" in (c.tags or [])]
    if len(mined) < 50:
        return False, f"too few mined meta situations: {len(mined)}"
    # Spot-check: a mined case still reconstructs its gold under the ladder.
    from plugin.evals.golden.score import score_meta_action_case

    sample = mined[0]
    scored = score_meta_action_case(sample)
    if not scored.passed:
        return False, f"sample mined case failed: {sample.id} {scored.checks}"
    return True, f"sections ok; mined_situations={len(mined)}"


def _llm_meta_choice_never_acts_while_look_owed() -> Tuple[bool, str]:
    """Live meta is LLM-chosen; post-act debt must still force re-perceive.

    Budgets/hard_block are not sanitize overrides. meta_choice stays on the
    text decision stack; controller must not pre-seed hard_block.
    """
    import ast
    from pathlib import Path

    from plugin.agent.consultation_routing import is_vision_task, resolve_reasoning_route
    from plugin.agent.executive.meta_action import MetaAction, MetaContext
    from plugin.agent.executive.meta_consultation import (
        resolve_meta_choice,
        sanitize_meta_choice,
    )

    msgs = [
        {"role": "system", "content": "Choose meta."},
        {"role": "user", "content": "Choose the next meta-action."},
    ]
    route = resolve_reasoning_route("perception", msgs, usecase="meta_choice")
    if is_vision_task(route.task) or route.task != "decision":
        return False, f"meta_choice routed to {route.task}"

    ctx = MetaContext(
        post_action_look_owed=True,
        awaiting_verification=True,
        has_grounded_action=True,
        last_action_surprised=False,
    )
    forced = sanitize_meta_choice(
        {"meta_action": "act", "why": "skip look", "confidence": 0.99}, ctx
    )
    if forced is None or forced.action is not MetaAction.PERCEIVE:
        return False, f"sanitize allowed act while look owed: {forced}"

    class _ActChooser:
        def choose(self, system, packet):
            return {"meta_action": "act", "why": "skip", "confidence": 0.99}

    choice = resolve_meta_choice(ctx, chooser=_ActChooser())
    if choice.action is not MetaAction.PERCEIVE:
        return False, f"resolve allowed {choice.action} while look owed"

    # No env kill switch / no ladder fallback in the live meta module.
    import plugin.agent.executive.meta_consultation as meta_mod

    if hasattr(meta_mod, "meta_llm_enabled"):
        return False, "meta_llm_enabled flag still present"
    meta_src = Path(meta_mod.__file__).read_text(encoding="utf-8")
    if "os.getenv" in meta_src and "META" in meta_src:
        return False, "meta_consultation still reads a META env kill switch"
    if "ladder_fallback" in meta_src:
        return False, "meta_consultation still has ladder_fallback"
    if "from plugin.agent.executive.hierarchy import decision_ladder" in meta_src:
        return False, "meta_consultation still imports decision_ladder"

    ctrl = Path(__file__).resolve().parents[1] / "agent" / "controller.py"
    tree = ast.parse(ctrl.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "hard_block":
                    return False, "controller still assigns hard_block"
    return True, f"meta_choice→{route.task}; look-owed→{choice.action.value}"


def _invoke_requires_referent_selection() -> Tuple[bool, str]:
    """Live 235148: Forward grounded ≠ patient selected — block pretend-commit invoke.

    Live 173658 exception: honest act_clear on an open overlay already scoped the
    patient via reveal — sticky ambiguous must not deadlock invoke.
    """
    from plugin.agent.decision_consultation import (
        DecisionBrief,
        TaskState,
        sanitize_decision,
    )

    # Conversation (no overlay act_clear): still require a selected patient.
    brief = DecisionBrief(
        goal={
            "operation": "forward_message",
            "source_conversation": "Alice",
            "source_query": "goal_token",
            "destination": "Bob",
        },
        world={"surface": "conversation"},
        capabilities=["invoke_affordance", "select_content", "observe"],
        meta_action="act",
        task_state=TaskState(
            phase="invoke_forward",
            source_chat_open=True,
            content_located=True,
            referent_selected=False,
            referent_binding_status="ambiguous",
            selection_consistent=True,
        ),
        search_episode={"status": "complete", "chosen_label": "https://example.test/goal_token"},
    )
    rejected = sanitize_decision(
        {"capability": "invoke_affordance", "target": "Forward", "why": "toolbar"},
        brief,
    )
    if rejected.ok:
        return False, "invoke must fail without selected/ambiguous-free referent"
    brief.task_state.referent_selected = True
    brief.task_state.referent_binding_status = "provisional"
    ok = sanitize_decision(
        {
            "capability": "invoke_affordance",
            "target": "Forward",
            "why": "toolbar",
            "confidence": 0.9,
        },
        brief,
    )
    if not ok.ok:
        return False, f"invoke with selected referent must pass, got {ok.why}"

    # Overlay + act_clear + sticky ambiguous: must allow commit (173658).
    overlay = DecisionBrief(
        goal={
            "operation": "forward_message",
            "source_conversation": "Alice",
            "source_query": "goal_token",
            "destination": "Bob",
        },
        world={"surface": "context_menu"},
        capabilities=["invoke_affordance", "select_content", "observe"],
        meta_action="act",
        act_clear=True,
        affordance_stance="act_clear",
        task_state=TaskState(
            phase="invoke_forward",
            source_chat_open=True,
            content_located=True,
            referent_selected=False,
            referent_binding_status="ambiguous",
            selection_consistent=True,
        ),
        search_episode={"status": "complete", "chosen_label": "https://example.test/goal_token"},
    )
    cleared = sanitize_decision(
        {
            "capability": "invoke_affordance",
            "target": "Forward",
            "why": "menu act_clear",
            "confidence": 0.9,
        },
        overlay,
    )
    if not cleared.ok:
        return False, f"act_clear overlay invoke must pass sticky ambiguous, got {cleared.why}"
    return True, "invoke_gated_on_referent_selection"


def _referent_repair_owed_forces_act_not_explore() -> Tuple[bool, str]:
    """After wrong-target invoke, meta must ACT repair — not EXPLORE/observe thrash."""
    from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice

    scored = select_meta_action(
        MetaContext(
            referent_repair_owed=True,
            route_discovery_owed=True,
            incomplete_reveal=True,
            has_grounded_action=True,
        )
    )
    if scored.action is not MetaAction.ACT:
        return False, f"scorer must hard-return ACT on referent_repair, got {scored}"
    sanitized = sanitize_meta_choice(
        {"meta_action": "explore", "why": "probe", "confidence": 0.95},
        MetaContext(referent_repair_owed=True, has_grounded_action=True),
    )
    if sanitized is None or sanitized.action is not MetaAction.ACT:
        return False, f"sanitize must force ACT repair, got {sanitized}"
    return True, "referent_repair_forces_act"


def _act_clear_requires_control_geometry() -> Tuple[bool, str]:
    """Live 171627: label-only Forward without point/bounds is not act_clear."""
    from plugin.agent.goal import Goal
    from plugin.agent.unified_cognition import UnifiedProposal, apply_affordance_stance

    proposal = UnifiedProposal(
        world_model={
            "surface": "context_menu",
            "objects": [
                {"id": "fwd", "kind": "menu_item", "text": "Forward"},
            ],
        },
        observed_state={"surface": "context_menu"},
        suggested_actions=[
            {
                "rank": 1,
                "family": "invoke_affordance",
                "text": "Forward",
                "confidence": 0.95,
            }
        ],
        affordance_qc={"expected_found": True, "missing": []},
        affordance_stance="act_clear",
    )
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    apply_affordance_stance(proposal, goal=goal)
    if proposal.affordance_stance == "act_clear":
        return False, "label-only menu verb must not remain act_clear"
    if proposal.affordance_stance != "explore_needed":
        return False, f"expected explore_needed, got {proposal.affordance_stance}"
    return True, "act_clear_requires_control_geometry"


def _act_clear_act_rejects_observe() -> Tuple[bool, str]:
    """Live 171627: act_clear + meta ACT must not burn turns on Observe/Escape."""
    from plugin.agent.decision_consultation import (
        DecisionBrief,
        TaskState,
        sanitize_decision,
    )

    brief = DecisionBrief(
        goal={
            "operation": "forward_message",
            "source_conversation": "Alice",
            "source_query": "goal_token",
            "destination": "Bob",
        },
        world={"surface": "context_menu"},
        capabilities=[
            "invoke_affordance",
            "observe",
            "request_more_evidence",
            "reveal_actions",
            "dismiss_transient",
            "select_content",
        ],
        meta_action="act",
        act_clear=True,
        affordance_stance="act_clear",
        task_state=TaskState(
            phase="invoke_forward",
            source_chat_open=True,
            content_located=True,
            referent_selected=True,
            referent_binding_status="provisional",
            selection_consistent=True,
        ),
        perceptor_suggestions=[
            {
                "family": "invoke_affordance",
                "text": "Forward",
                "target_point": [1270, 332],
                "confidence": 0.9,
            }
        ],
    )
    for cap in ("observe", "reveal_actions", "dismiss_transient", "select_content"):
        rejected = sanitize_decision(
            {"capability": cap, "target": "Forward", "why": "look again"},
            brief,
        )
        if rejected.ok:
            return False, f"act_clear+ACT must reject {cap}"
    ok = sanitize_decision(
        {
            "capability": "invoke_affordance",
            "target": "Forward",
            "why": "commit",
            "confidence": 0.9,
        },
        brief,
    )
    if not ok.ok:
        return False, f"invoke under act_clear must pass, got {ok.why}"
    return True, "act_clear_act_rejects_observe"


def _overlay_invoke_binds_menu_geometry_not_content() -> Tuple[bool, str]:
    """Overlay Forward with menu geometry must not click the content URL."""
    from plugin.agent.goal import Goal
    from plugin.agent.unified_cognition import UnifiedProposal, proposal_to_action
    from plugin.worldmodel.entities.entity import Entity
    from plugin.worldmodel.model import WorldModel

    world = WorldModel(active_app="WhatsApp")
    content = Entity(
        id=9,
        entity_type="message",
        semantic_role="message",
        role="AXStaticText",
        label="https://example.test/zarooratwala",
        bounds=(280, 320, 200, 40),
        visible=True,
    )
    world.entities[9] = content
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    # Inventory carries the control point; world only has the URL patient.
    proposal = UnifiedProposal(
        observed_state={"surface": "context_menu"},
        world_model={
            "surface": "context_menu",
            "objects": [
                {
                    "id": "fwd",
                    "kind": "menu_item",
                    "text": "Forward",
                    "point": [1270, 332],
                },
                {
                    "id": "url",
                    "kind": "message",
                    "text": "https://example.test/zarooratwala",
                    "point": [310, 340],
                },
            ],
        },
        next_action={
            "family": "invoke_affordance",
            "text": "Forward",
            "target_point": [1270, 332],
            "coordinate_space": "screen",
            "confidence": 0.9,
        },
        confidence=0.9,
    )
    action, err = proposal_to_action(proposal, goal, world)
    if action is None:
        return False, f"menu-geometry invoke failed: {err}"
    if getattr(action, "target_entity_id", None) == 9:
        return False, "overlay Forward rebound to content URL entity"
    pt = getattr(action, "target_point", None)
    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
        return False, f"missing menu control point, got {pt}"
    if abs(float(pt[0]) - 1270.0) > 8 or abs(float(pt[1]) - 332.0) > 8:
        return False, f"point not menu geometry: {pt}"
    # Label-only inventory must refuse rather than click the URL.
    bare = UnifiedProposal(
        observed_state={"surface": "context_menu"},
        world_model={
            "surface": "context_menu",
            "objects": [{"id": "fwd", "kind": "menu_item", "text": "Forward"}],
        },
        next_action={
            "family": "invoke_affordance",
            "text": "Forward",
            "confidence": 0.9,
        },
        confidence=0.9,
    )
    action2, err2 = proposal_to_action(bare, goal, world)
    if action2 is not None or err2 != "overlay_verb_without_geometry":
        return False, f"label-only must refuse, got action={action2} err={err2}"
    return True, "overlay_invoke_binds_menu_geometry_not_content"


def _failed_reveal_episode_frees_meta_from_explore() -> Tuple[bool, str]:
    """Live 142848/181059: method miss advances intention; exhaustion frees meta."""
    from plugin.agent.affordance_frontier import AffordanceFrontier, finalize_reveal_handoff
    from plugin.agent.capabilities.reveal_actions import note_reveal_probe_handoff
    from plugin.agent.executive.intention_frame import (
        MethodStatus,
        active_intention_frame,
        mark_method_attempted,
        record_method_status,
    )
    from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice
    from plugin.agent.executive.sync import _route_discovery_meta_kwargs
    from plugin.agent.runtime.state import ExecutionState

    state = ExecutionState()
    note_reveal_probe_handoff(
        state, surface="context_menu", ttl=1, gesture="context_click"
    )
    # First settle miss → method advance under same intention (not episode death).
    frontier = AffordanceFrontier(surface="context_menu")
    status = finalize_reveal_handoff(state, frontier)
    if status.get("failed_reveal"):
        return False, f"first method miss must not terminate episode, got {status}"
    if not status.get("method_advance"):
        return False, f"expected method_advance, got {status}"
    iframe = active_intention_frame(state)
    if iframe is None:
        return False, "intention frame missing after reveal handoff"
    surviving_id = iframe.intention.id
    if not surviving_id:
        return False, "intention id missing"
    # Exhaust remaining methods via decision status (ledger alone is not a blocker).
    for mid in list(iframe.method_frontier.eligible_methods()):
        mark_method_attempted(iframe, mid)
        record_method_status(iframe, mid, MethodStatus.INEFFECTIVE.value)
    state.reveal_handoff = {
        "surface": "context_menu",
        "ttl": 1,
        "looks": 0,
        "incomplete_reveal": True,
        "probe_gesture": "select_content",
    }
    state.reveal_prefer_capability = "select_content"
    state.reveal_probe_mode = "select_content"
    status2 = finalize_reveal_handoff(state, frontier)
    if not status2.get("failed_reveal") and not status2.get("episode_terminal"):
        # Frame-derived exhaustion should mark terminal.
        from plugin.agent.executive.intention_frame import apply_derived_status, is_local_route_exhausted

        apply_derived_status(iframe)
        if not is_local_route_exhausted(iframe):
            return False, f"expected exhaustion after all methods, status={status2}"
    route_kw = _route_discovery_meta_kwargs(
        state,
        {
            "complete": True,
            "address_known": True,
            "chosen_label": "https://example.test/x",
        },
    )
    if route_kw.get("incomplete_reveal"):
        return False, f"exhausted episode must not keep incomplete, got {route_kw}"
    # Active intention with methods → EXPLORE; exhausted → not sticky ACT.
    active = select_meta_action(
        MetaContext(
            intention_explore_active=True,
            intention_locally_exhausted=False,
            has_grounded_action=False,
        )
    )
    if active.action is not MetaAction.EXPLORE:
        return False, f"active intention must EXPLORE, got {active}"
    # Exhausted intention must not sticky-force ACT (executive regains choice).
    exhausted = select_meta_action(
        MetaContext(
            reveal_episode_failed=True,
            intention_locally_exhausted=True,
            intention_explore_active=False,
            has_grounded_action=False,
            probe_exhausted=True,
        )
    )
    if exhausted.action is MetaAction.ACT and "escalat" in (exhausted.reason or "").lower():
        return False, f"exhausted must not sticky-force ACT escalate, got {exhausted}"
    # Active intention still wins over ACT proposals via sanitize.
    keep = sanitize_meta_choice(
        {"meta_action": "act", "why": "force", "confidence": 0.9},
        MetaContext(intention_explore_active=True, has_grounded_action=False),
    )
    if keep is None or keep.action is not MetaAction.EXPLORE:
        return False, f"sanitize must keep EXPLORE while intention active, got {keep}"
    # Pending (non-failed) incomplete still forces EXPLORE — flexibility preserved.
    pending = sanitize_meta_choice(
        {"meta_action": "act", "why": "click again", "confidence": 0.9},
        MetaContext(
            route_discovery_owed=True,
            incomplete_reveal=True,
            reveal_episode_failed=False,
            probe_exhausted=False,
        ),
    )
    if pending is None or pending.action is not MetaAction.EXPLORE:
        return False, f"pending incomplete must still → EXPLORE, got {pending}"
    return True, "failed_reveal_episode_frees_meta"


def _intention_frame_survives_method_miss() -> Tuple[bool, str]:
    """181059 golden: METHOD_INEFFECTIVE keeps intention; forbids unmotivated Observe."""
    from plugin.agent.decision_consultation import DecisionBrief, TaskState, sanitize_decision
    from plugin.agent.executive.intention_frame import (
        MethodOutcome,
        classify_method_outcome,
        evaluate_intention_success,
        mark_method_attempted,
        seed_reveal_explore_frame,
    )
    from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.executive.intention_frame import push_intention_frame

    outcome, fail = classify_method_outcome(
        execution_ok=True, observation_quality=0.93, effect_present=False
    )
    if outcome != MethodOutcome.EFFECT_ABSENT.value or fail != "method_ineffective":
        return False, f"high-quality miss must be METHOD_INEFFECTIVE, got {outcome}/{fail}"
    uncertain, ufail = classify_method_outcome(
        execution_ok=True, observation_quality=0.2, effect_present=False
    )
    if uncertain != "effect_uncertain":
        return False, f"low-quality obs must be EFFECT_UNCERTAIN, got {uncertain}"

    frame = seed_reveal_explore_frame()
    iid = frame.intention.id
    mark_method_attempted(frame, "reveal_context_click")
    if frame.intention.id != iid:
        return False, "intention id must be immutable/survive"
    if "reveal_hover" not in frame.method_frontier.eligible_methods():
        return False, "sibling methods must remain eligible"
    # Method effect without Forward ≠ intention success.
    if evaluate_intention_success(
        frame,
        world={"surface": "selection_mode", "objects": [{"text": "Reply"}]},
        affordance_stance="explore_needed",
    ):
        return False, "Reply-only surface must not achieve forwarding intention"

    state = ExecutionState()
    push_intention_frame(state, frame)
    scored = select_meta_action(
        MetaContext(intention_explore_active=True, has_grounded_action=False)
    )
    if scored.action is not MetaAction.EXPLORE:
        return False, f"must keep EXPLORE while methods remain, got {scored}"

    brief = DecisionBrief(
        goal={"operation": "forward_message", "source_query": "x"},
        world={"surface": "conversation"},
        capabilities=["reveal_actions", "select_content", "observe"],
        meta_action="explore",
        effect_closure={"intention_active": True},
        task_state=TaskState(phase="invoke_forward", source_chat_open=True),
    )
    rejected = sanitize_decision(
        {"capability": "observe", "why": "look again"}, brief
    )
    if rejected.ok:
        return False, "unmotivated observe must be rejected under active intention"
    return True, "intention_frame_survives_method_miss"


def _forward_picker_requires_destination_before_forward() -> Tuple[bool, str]:
    """Live 184742 safety: commit Forward only after inventory-selected destination."""
    from plugin.agent.decision_consultation import DecisionBrief, TaskState, sanitize_decision
    from plugin.agent.goal import Goal
    from plugin.agent.unified_cognition import UnifiedProposal, apply_affordance_stance

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    # Picker open; background selection status + disabled Forward; no dest row.
    proposal = UnifiedProposal(
        observed_state={"surface": "forward_picker"},
        world_model={
            "surface": "forward_picker",
            "objects": [
                {
                    "id": "sel",
                    "text": "1 Selected",
                    "kind": "status",
                    "owner_surface": "conversation",
                    "semantic_role": "source_message_selection",
                },
                {
                    "id": "fwd",
                    "text": "Forward",
                    "kind": "button",
                    "point": [1400, 900],
                    "enabled": False,
                    "owner_surface": "forward_picker",
                },
                {
                    "id": "papaji",
                    "text": "Papaji",
                    "kind": "row",
                    "point": [900, 400],
                    "owner_surface": "forward_picker",
                },
            ],
        },
        affordance_stance="act_clear",
        raw={},
    )
    apply_affordance_stance(proposal, goal=goal)
    if proposal.affordance_stance == "act_clear":
        return False, "must not act_clear Forward without destination selected"
    brief = DecisionBrief(
        goal={
            "operation": "forward_message",
            "source_query": "zarooratwala",
            "destination": "Tanmay",
            "target_contact": "Tanmay",
        },
        world={
            "surface": "forward_picker",
            "objects": [
                {"text": "1 Selected", "kind": "status", "owner_surface": "conversation"},
                {"text": "Forward", "point": [1400, 900], "enabled": False},
                {"text": "Papaji", "point": [900, 400], "owner_surface": "forward_picker"},
            ],
        },
        capabilities=["invoke_affordance", "type_query", "observe"],
        meta_action="act",
        affordance_stance="explore_needed",
        act_clear=False,
        task_state=TaskState(phase="choose_destination", source_chat_open=True),
    )
    rejected = sanitize_decision(
        {"capability": "invoke_affordance", "target": "Forward", "why": "send it"},
        brief,
    )
    if rejected.ok:
        return False, "Forward invoke must be rejected until destination selected"
    brief.world["objects"] = [
        {"text": "Tanmay", "point": [900, 420], "selected": False, "owner_surface": "forward_picker"},
        {"text": "Forward", "point": [1400, 900]},
    ]
    allowed = sanitize_decision(
        {"capability": "invoke_affordance", "target": "Tanmay", "why": "pick dest"},
        brief,
    )
    if not allowed.ok:
        return False, f"invoke destination row must be allowed, got {allowed.why}"
    proposal2 = UnifiedProposal(
        observed_state={"surface": "forward_picker"},
        world_model={
            "surface": "forward_picker",
            "objects": [
                {
                    "text": "Tanmay",
                    "kind": "row",
                    "point": [900, 420],
                    "selected": True,
                    "matches_goal": True,
                    "owner_surface": "forward_picker",
                },
                {
                    "text": "Forward",
                    "kind": "button",
                    "point": [1400, 900],
                    "enabled": True,
                    "owner_surface": "forward_picker",
                },
            ],
        },
        affordance_stance="explore_needed",
        raw={},
    )
    apply_affordance_stance(proposal2, goal=goal)
    if proposal2.affordance_stance != "act_clear":
        return False, f"selected dest + enabled Forward must act_clear, got {proposal2.affordance_stance}"
    return True, "forward_picker_requires_destination_before_forward"


def _surface_ownership_blocks_cross_surface_destination() -> Tuple[bool, str]:
    """Live 184742 intelligence: source-surface selection ≠ destination_selected."""
    from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice
    from plugin.agent.goal import Goal
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import (
        _destination_search_perception_objective,
        build_decision_packet,
    )
    from plugin.agent.world_document import normalize_document, scrub_cross_surface_selection_beliefs
    from plugin.agent.features import StateFeatures
    from plugin.worldmodel.model import WorldModel

    # Belief owned by background conversation cannot assert destination_selected.
    doc = normalize_document(
        {
            "surface": "forward_picker",
            "open_conversation": "Pallavi",
            "objects": [
                {
                    "text": "1 Selected",
                    "kind": "status",
                    "owner_surface": "conversation",
                    "semantic_role": "source_message_selection",
                },
                {
                    "text": "Search",
                    "kind": "search_input",
                    "point": [800, 200],
                    "owner_surface": "forward_picker",
                },
                {"text": "Papaji", "kind": "row", "point": [800, 400], "owner_surface": "forward_picker"},
            ],
            "beliefs": [
                {
                    "predicate": "destination_selected",
                    "value": True,
                    "confidence": 0.9,
                    "evidence": ["saw selection count chrome"],
                    "owner_surface": "conversation",
                    "semantic_role": "source_message_selection",
                },
                {
                    "predicate": "source_message_selected_count",
                    "value": True,
                    "confidence": 0.95,
                    "evidence": ["selection bar"],
                    "owner_surface": "conversation",
                    "semantic_role": "source_message_selection",
                },
            ],
        },
        frame=7,
    )
    dest_beliefs = [
        b
        for b in (doc.get("beliefs") or [])
        if str(b.get("predicate") or "") == "destination_selected"
    ]
    if not dest_beliefs or bool(dest_beliefs[0].get("value")):
        return False, f"cross-surface destination_selected must scrub to false, got {dest_beliefs}"
    if not dest_beliefs[0].get("rejected_evidence"):
        return False, "scrub must record rejected_evidence"

    # Metamorphic: picker-owned selected recipient keeps destination_selected.
    ok_doc = scrub_cross_surface_selection_beliefs(
        {
            "surface": "forward_picker",
            "objects": [
                {
                    "text": "Tanmay",
                    "selected": True,
                    "matches_goal": True,
                    "owner_surface": "forward_picker",
                    "semantic_role": "recipient",
                }
            ],
            "beliefs": [
                {
                    "predicate": "destination_selected",
                    "value": True,
                    "confidence": 0.9,
                    "owner_surface": "forward_picker",
                    "semantic_role": "destination_selection",
                    "evidence": ["recipient checkbox checked in picker"],
                }
            ],
        }
    )
    kept = [
        b
        for b in (ok_doc.get("beliefs") or [])
        if str(b.get("predicate") or "") == "destination_selected"
    ]
    if not kept or not bool(kept[0].get("value")):
        return False, "picker-owned destination_selected must survive"

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    obj = _destination_search_perception_objective(goal, doc)
    if obj is None or "destination" not in str(obj.get("objective") or "").lower():
        return False, f"expected destination SEARCH perception objective, got {obj}"
    if obj.get("destination_selected") is not False:
        return False, "objective must report destination_selected=false"

    # Meta SEARCH when destination_search_needed.
    scored = select_meta_action(
        MetaContext(
            destination_search_needed=True,
            has_grounded_action=True,
            act_clear=False,
            search_has_criteria=True,
        )
    )
    if scored.action is not MetaAction.SEARCH:
        return False, f"meta must SEARCH for unresolved destination, got {scored}"
    forced = sanitize_meta_choice(
        {"meta_action": "act", "why": "forward now", "confidence": 0.9},
        MetaContext(destination_search_needed=True, act_clear=False, has_grounded_action=True),
    )
    if forced is None or forced.action is not MetaAction.SEARCH:
        return False, f"sanitize must force SEARCH, got {forced}"

    # Packet carries ownership addendum + active_interaction_surface.
    state = ExecutionState()
    state.unified_world_document = doc
    state.goal = goal
    world = WorldModel()
    features = StateFeatures(app="WhatsApp", extras={})
    packet = build_decision_packet(goal, world, features, execution_state=state)
    po = packet.get("perception_objective") or {}
    if not po.get("questions"):
        return False, "packet must carry destination perception questions"
    if str((packet.get("observation") or {}).get("active_interaction_surface") or "") != "forward_picker":
        return False, "observation must stamp active_interaction_surface=forward_picker"
    return True, "surface_ownership_blocks_cross_surface_destination"


def _semantic_perception_zero_cross_surface_contamination() -> Tuple[bool, str]:
    """Architect: perception goldens score world understanding; contamination must be 0."""
    from plugin.evals.perception_semantic.metamorphic import expand_family
    from plugin.evals.perception_semantic.projector import assert_production_projector
    from plugin.evals.perception_semantic.schema import load_cases
    from plugin.evals.perception_semantic.score import score_corpus

    seeded = load_cases()
    if not seeded:
        return False, "no semantic perception fixtures loaded"
    cases = []
    for c in seeded:
        cases.extend(expand_family(c) if not c.metamorphic_of else [c])
    report = score_corpus(cases)
    contam = float(report.get("cross_surface_contamination_rate") or 0.0)
    if contam > 0:
        return False, f"cross_surface_contamination_rate={contam}"
    if int(report.get("failed") or 0) > 0:
        fails = [
            d.get("case_id")
            for d in (report.get("details") or [])
            if not d.get("passed")
        ]
        return False, f"semantic scores failed: {fails[:6]}"
    for c in cases:
        if c.metamorphic_of and not c.packet:
            continue
        pr = assert_production_projector(c)
        if not pr.get("ok"):
            return False, f"production projector failed for {c.id}: {pr}"
    return True, "semantic_perception_zero_cross_surface_contamination"


def _child_prereq_spawn_resume_reranks() -> Tuple[bool, str]:
    """Gates 12+15: PRECONDITION_MISSING spawns child; resume re-ranks (no blind replay)."""
    from plugin.agent.executive.intention_frame import (
        EffectSpec,
        MethodProvenance,
        MethodSpec,
        active_intention_frame,
        ensure_prereq_child_or_next_method,
        intention_stack_of,
        mark_method_attempted,
        push_intention_frame,
        resume_parent_after_child,
        seed_reveal_explore_frame,
    )
    from plugin.agent.runtime.state import ExecutionState

    state = ExecutionState()
    parent = seed_reveal_explore_frame()
    push_intention_frame(state, parent)
    mark_method_attempted(parent, "reveal_context_click")
    # Force hover to the head so the prereq path is exercised.
    parent.method_frontier.known_untried = [
        "reveal_hover",
        *[
            m
            for m in parent.method_frontier.known_untried
            if m != "reveal_hover"
        ],
    ]
    nxt = ensure_prereq_child_or_next_method(
        state,
        parent,
        world={"surface": "conversation"},
        predicates={"source_object_selected": False},
    )
    if nxt is None or nxt.capability != "select_content":
        return False, f"expected select child method, got {nxt}"
    stack = intention_stack_of(state)
    if len(stack) < 2:
        return False, f"expected parent+child stack, got {len(stack)}"
    if not stack[0].suspended_by_child:
        return False, "parent must be suspended_by_child"
    if "reveal_hover" not in stack[0].method_frontier.currently_ineligible:
        return False, "blocked method must be ineligible, not attempted-as-failure"
    if "reveal_hover" in stack[0].method_frontier.attempted:
        return False, "prereq miss must not mark hover attempted"
    child = active_intention_frame(state)
    if child is None or child.parent_intention_id != parent.intention.id:
        return False, "active frame must be the child"
    # Observed Forward appears while child completes — must re-rank, not force hover.
    parent.method_frontier.catalog["observed_forward"] = MethodSpec(
        id="observed_forward",
        capability="invoke_affordance",
        target_binding="source_object",
        expected_effect=EffectSpec(success_any=["forward_affordance_grounded"]),
        provenance=MethodProvenance.OBSERVED.value,
        reversibility=0.5,
        risk=0.2,
    )
    parent.method_frontier.newly_discovered.append("observed_forward")
    status = resume_parent_after_child(
        state,
        world={
            "surface": "conversation",
            "source_object_selected": True,
            "objects": [{"text": "Forward", "point": [10, 10]}],
        },
        affordance_stance="explore_needed",
        grounded_forward=False,
    )
    if not status.get("resumed"):
        return False, f"expected resume, got {status}"
    rerank = list(status.get("rerank") or [])
    if not rerank:
        return False, f"expected non-empty re-rank after resume, got {status}"
    # Observed provenance must outrank blind replay of the blocked hover method.
    if rerank[0] == "reveal_hover":
        return False, f"must not blindly replay hover when observed_forward exists: {rerank}"
    if "observed_forward" not in rerank:
        return False, f"observed_forward missing from re-rank: {rerank}"
    return True, "child_prereq_spawn_resume_reranks"


def _act_clear_stops_route_explore_latch() -> Tuple[bool, str]:
    """Live 001141: open menu with Forward must not keep forcing EXPLORE/reveal."""
    from types import SimpleNamespace

    from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice
    from plugin.agent.executive.sync import _route_discovery_meta_kwargs
    from plugin.agent.goal import Goal
    from plugin.agent.unified_cognition import (
        UnifiedProposal,
        apply_affordance_stance,
        proposal_to_action,
    )
    from plugin.worldmodel.entities.entity import Entity
    from plugin.worldmodel.model import WorldModel

    # Perceptor: inventory has Forward on context_menu → act_clear, not reveal.
    proposal = UnifiedProposal(
        world_model={
            "surface": "context_menu",
            "objects": [
                {
                    "id": "fwd",
                    "kind": "menu_item",
                    "text": "Forward",
                    "point": [1270, 332],
                    "matches_goal": True,
                },
                {
                    "id": "url",
                    "kind": "message",
                    "text": "https://example.test/zarooratwala",
                    "point": [310, 340],
                },
            ],
        },
        observed_state={"surface": "context_menu"},
        visible_objects=[
            {
                "id": "fwd",
                "kind": "menu_item",
                "text": "Forward",
                "point": [1270, 332],
            }
        ],
        suggested_actions=[
            {
                "rank": 1,
                "family": "reveal_actions",
                "text": "Forward",
                "confidence": 0.9,
                "why": "still exploring",
            }
        ],
        affordance_qc={"expected_found": True, "missing": [], "notes": ""},
        affordance_stance="explore_needed",
    )
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    apply_affordance_stance(proposal, goal=goal)
    if proposal.affordance_stance != "act_clear":
        return False, f"stance must coerce to act_clear, got {proposal.affordance_stance}"
    head_fam = str((proposal.suggested_actions or [{}])[0].get("family") or "")
    if head_fam != "invoke_affordance":
        return False, f"top suggestion must be invoke_affordance, got {head_fam}"

    # Sticky handoff + prior grounded stamp must still clear route debt.
    st = SimpleNamespace(
        reveal_handoff={"incomplete_reveal": True, "surface": "context_menu"},
        last_effect_closure={"incomplete_reveal": True, "modes": ["incomplete_reveal"]},
        last_selection_consistency=None,
        last_failed_motor_key="",
        last_grounded_affordance_set=[{"label": "Forward", "family": "invoke_affordance"}],
        reveal_gesture_attempts=2,
        reveal_prefer_capability="",
        epistemic_success_at=1.0,
        affordance_grounded_at=1.0,  # already stamped once (the bug)
        referent_selected_at=0.0,
        last_affordance_stance="act_clear",
        last_unified_proposal=proposal.to_dict(),
    )
    route_kw = _route_discovery_meta_kwargs(
        st,
        {
            "complete": True,
            "address_known": True,
            "chosen_label": "https://example.test/zarooratwala",
        },
    )
    if route_kw.get("route_discovery_owed") or route_kw.get("incomplete_reveal"):
        return False, f"grounded/act_clear must clear route debt, got {route_kw}"
    if not route_kw.get("act_clear"):
        return False, f"act_clear flag missing: {route_kw}"

    scored = select_meta_action(
        MetaContext(
            act_clear=True,
            route_discovery_owed=True,
            incomplete_reveal=True,
            has_grounded_action=True,
        )
    )
    if scored.action is not MetaAction.ACT:
        return False, f"scorer must ACT when act_clear, got {scored}"
    sanitized = sanitize_meta_choice(
        {"meta_action": "explore", "why": "still looking", "confidence": 0.95},
        MetaContext(act_clear=True, has_grounded_action=True),
    )
    if sanitized is None or sanitized.action is not MetaAction.ACT:
        return False, f"sanitize must force ACT when act_clear, got {sanitized}"

    # Overlay verb must not rebind onto content URL geometry.
    world = WorldModel(active_app="WhatsApp")
    menu = Entity(
        id=7,
        entity_type="control",
        semantic_role="menu_item",
        role="AXMenuItem",
        label="Forward",
        bounds=(1200, 300, 140, 40),
        visible=True,
    )
    content = Entity(
        id=9,
        entity_type="message",
        semantic_role="message",
        role="AXStaticText",
        label="https://example.test/zarooratwala",
        bounds=(280, 320, 200, 40),
        visible=True,
    )
    world.entities[7] = menu
    world.entities[9] = content
    act_proposal = UnifiedProposal(
        observed_state={"surface": "context_menu"},
        world_model={"surface": "context_menu"},
        next_action={
            "family": "invoke_affordance",
            "text": "Forward",
            "confidence": 0.9,
        },
        confidence=0.9,
    )
    action, err = proposal_to_action(act_proposal, goal, world)
    if action is None:
        return False, f"invoke Forward on menu failed: {err}"
    if getattr(action, "target_entity_id", None) == 9:
        return False, "overlay Forward rebound to content URL entity"
    if getattr(action, "target_entity_id", None) not in {7, None}:
        return False, f"unexpected bind target={action.target_entity_id} err={err}"
    if getattr(action, "target_point", None) is None and getattr(action, "target_entity_id", None) is None:
        return False, "overlay Forward invoke lost geometry"
    return True, "act_clear_stops_route_explore_latch"


def _selection_mode_not_context_menu() -> Tuple[bool, str]:
    """Selection toolbar chrome must classify as selection_mode, not context_menu."""
    from plugin.agent.world_critic import critique_world_proposal

    prior = {"surface": "conversation", "open_conversation": "Alice", "objects": []}
    proposal = {
        "surface": "context_menu",
        "open_conversation": "Alice",
        "objects": [
            {"id": "s", "kind": "status_text", "text": "1 Selected", "point": [900, 60]},
            {"id": "f", "kind": "button", "text": "Forward", "point": [980, 990]},
            {
                "id": "m",
                "kind": "message_bubble",
                "text": "https://example.test/goal",
                "matches_goal": True,
                "point": [1200, 200],
            },
        ],
    }
    result = critique_world_proposal(prior, proposal, last_action="select_content")
    accepted = getattr(result, "accepted_document", None) or {}
    if not isinstance(accepted, dict):
        return False, f"unexpected critic result type {type(result)}"
    surf = str(accepted.get("surface") or "").strip().lower()
    if surf != "selection_mode":
        return False, f"expected selection_mode, got {surf!r}"
    return True, "selection_mode_coerced"


def _wrong_selection_reverts_not_forwards() -> Tuple[bool, str]:
    """Live 132831: goal-inconsistent '2 Selected' must revert_effects, not Forward."""
    from plugin.agent.brain import apply_surprise_explanation
    from plugin.agent.capabilities.revert_effects import (
        analyze_revert_plan,
        approve_revert_plan,
        selection_consistency_error,
    )
    from plugin.agent.decision_consultation import DecisionOutcome
    from plugin.agent.reflect_diagnosis import seed_reflect_diagnosis_from_measured
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import finalize_surprise_explanation

    bad_doc = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [
            {"id": "sel", "kind": "status_text", "text": "2 Selected", "point": [900, 60]},
            {"id": "fwd", "kind": "button", "text": "Forward", "point": [981, 990]},
            {
                "id": "z",
                "kind": "message_bubble",
                "text": "https://www.zarooratwala.com/",
                "matches_goal": True,
                "point": [1191, 201],
            },
            {
                "id": "c",
                "kind": "message_bubble",
                "text": "Chunni ko bhi Prabal se baat karna hai...",
                "matches_goal": False,
                "point": [1124, 227],
            },
        ],
    }
    sel = selection_consistency_error(
        bad_doc, goal_referents=["zarooratwala", "https://www.zarooratwala.com"]
    )
    if sel.get("consistent") is not False:
        return False, f"expected inconsistent selection, got {sel}"

    packet = {
        "action": {
            "family": "select_content",
            "target": "zarooratwala",
            "executor_ok": True,
            "intended_point": [1191, 201],
            "motor_landed_point": [1124, 227],
        },
        "expected": {"surface": "conversation"},
        "actual": {
            "matched": True,
            "predicted_surface": "conversation",
            "observed_surface": "conversation",
        },
        "measured": {"geometry_mismatch": True},
        "goal": {"link_query": "zarooratwala"},
        "post_world": bad_doc,
    }
    seed = seed_reflect_diagnosis_from_measured(packet)
    if seed.repair.kind != "invoke_revert_effects":
        return False, f"seed repair={seed.repair.kind!r} (want invoke_revert_effects)"
    if seed.repair.capability != "revert_effects":
        return False, f"seed capability={seed.repair.capability!r}"

    plan = analyze_revert_plan(
        document=bad_doc,
        selection_consistency=sel,
        goal_referents=["zarooratwala"],
    )
    plan = approve_revert_plan(plan, auto=True)
    if not plan.approved or not plan.steps:
        return False, f"plan not approved: {plan.to_dict()}"
    if plan.steps[0].realization != "press_escape":
        return False, f"first realization={plan.steps[0].realization!r}"

    expl = finalize_surprise_explanation(
        {"cause": "unknown", "confidence": 0.2, "recommended_next": "reperceive"},
        reflect_packet=packet,
    )
    state = ExecutionState()
    state.perception_mode = "reflect"
    state.last_surprise_explanation = expl
    out = apply_surprise_explanation(
        DecisionOutcome(
            ok=True,
            capability="observe",
            target="",
            why="model_requested_observe",
            confidence=0.3,
            realization="llm_decision",
        ),
        state,
    )
    if out.capability != "revert_effects":
        return False, f"brain chose {out.capability!r} (want revert_effects)"

    # Regression: correct 1 Selected still follows Forward.
    good_packet = {
        "action": {
            "family": "invoke_affordance",
            "target": "Forward",
            "executor_ok": True,
            "executor_message": "AXPress 'Forward' in background (no foreground)",
            "intended_point": [1400.0, 400.0],
        },
        "expected": {"surface": "forward_picker"},
        "actual": {
            "matched": False,
            "predicted_surface": "forward_picker",
            "observed_surface": "conversation",
        },
        "measured": {"executor_ok": True},
        "goal": {"link_query": "zarooratwala"},
        "post_world": {
            "surface": "conversation",
            "objects": [
                {"id": "sel", "kind": "status_text", "text": "1 Selected"},
                {
                    "id": "fwd",
                    "kind": "button",
                    "text": "Forward",
                    "point": [520, 920],
                },
                {
                    "id": "msg",
                    "kind": "message_bubble",
                    "text": "ZarooratWala - Fresh Groceries",
                    "matches_goal": True,
                },
            ],
        },
    }
    good_seed = seed_reflect_diagnosis_from_measured(good_packet)
    if good_seed.repair.kind != "follow_observed_transition":
        return False, f"145239 regression: repair={good_seed.repair.kind!r}"
    return True, "wrong selection→revert_effects; correct selection→Forward"


def _barren_filter_chip_backtracks_not_ig_thrash() -> Tuple[bool, str]:
    """Start-anywhere: typed filter_chip + needed message/link → backtrack/revert.

    Cold start (empty effect_trace) must still recover. No chip-label allowlist
    in core — fixture uses generic filter_chip observation.
    """
    from plugin.agent.capabilities.branch_fitness import compute_branch_fitness
    from plugin.agent.capabilities.dispatch import can_dispatch
    from plugin.agent.capabilities.revert_effects import (
        PRESS_ESCAPE,
        analyze_revert_plan,
        approve_revert_plan,
    )
    from plugin.agent.reflect_diagnosis import seed_reflect_diagnosis_from_measured

    if not can_dispatch("backtrack"):
        return False, "backtrack alias not dispatchable (want ≡ revert_effects)"

    doc = {
        "surface": "search",
        "open_conversation": "",
        "objects": [
            {"text": "MediaFilter", "kind": "filter_chip", "restricts": "media"},
            {"text": "thumb", "kind": "media"},
        ],
    }
    fit = compute_branch_fitness(
        doc,
        needed_kinds=["message", "message_bubble", "link"],
        goal_referents=["example-link"],
    )
    if fit.get("admissible") is not False:
        return False, f"expected unfit branch, got {fit}"

    plan = analyze_revert_plan(
        document=doc,
        goal_referents=["example-link"],
        effect_trace=[],
        branch_fitness=fit,
    )
    plan = approve_revert_plan(plan, auto=True)
    if not plan.approved or not plan.steps:
        return False, f"plan not approved: {plan.to_dict()}"
    if plan.steps[0].realization != PRESS_ESCAPE:
        return False, f"first realization={plan.steps[0].realization!r}"

    seed = seed_reflect_diagnosis_from_measured(
        {
            "action": {
                "family": "compose_search_query",
                "target": "example-link",
                "executor_ok": True,
            },
            "expected": {"surface": "search"},
            "actual": {
                "matched": True,
                "predicted_surface": "search",
                "observed_surface": "search",
            },
            "goal": {"link_query": "example-link"},
            "post_world": doc,
            "branch_fitness": fit,
        }
    )
    if seed.repair.kind != "invoke_revert_effects":
        return False, f"seed repair={seed.repair.kind!r}"
    if seed.recommended_next != "explore":
        return False, f"recommended_next={seed.recommended_next!r} (want explore)"
    # Live-mined 140713 OCR world (open='• Videos' + duration thumbs) must also
    # recover after host overlay tags filter_chip — not only generic fixtures.
    from plugin.agent.apps.whatsapp import WhatsAppOverlay

    live_doc = WhatsAppOverlay().enrich_world_document(
        {
            "surface": "search",
            "open_conversation": "• Videos",
            "objects": [
                {"text": "• Videos", "kind": "chip"},
                {"text": "1:34", "kind": "media"},
                {"text": "2:10", "kind": "media"},
            ],
        }
    )
    live_fit = compute_branch_fitness(
        live_doc,
        needed_kinds=["message", "message_bubble", "link"],
        goal_referents=["zarooratwala"],
    )
    if live_fit.get("admissible") is not False:
        return False, f"140713 live OCR world still admissible: {live_fit}"
    live_plan = analyze_revert_plan(
        document=live_doc,
        goal_referents=["zarooratwala"],
        effect_trace=[],
        branch_fitness=live_fit,
    )
    live_plan = approve_revert_plan(live_plan, auto=True)
    if not live_plan.approved or live_plan.steps[0].realization != PRESS_ESCAPE:
        return False, f"140713 live plan={live_plan.to_dict()}"
    return True, "filter_chip cold start + live 140713 Videos OCR → press_escape/backtrack"


def _recoverability_substrate_wired_for_goldens() -> Tuple[bool, str]:
    """Agent structure/behavior the recoverability goldens assume must stay wired.

    Goldens alone can pass against stubs; this gate locks catalog aliases, state
    fields, meta packet fitness, overlay tagging, undo_hint LIFO, brain/reflect
    consumption, BACKTRACK→revert_effects, and the end-to-end unfit→backtrack
    path so live agents remain able to satisfy those goldens.
    """
    from pathlib import Path

    from plugin.agent.apps.whatsapp import WhatsAppOverlay
    from plugin.agent.brain import apply_surprise_explanation
    from plugin.agent.capabilities.branch_fitness import compute_branch_fitness
    from plugin.agent.capabilities.catalog import model_allowed_actions, spec_by_name
    from plugin.agent.capabilities.dispatch import can_dispatch
    from plugin.agent.capabilities.revert_effects import (
        PRESS_ESCAPE,
        analyze_revert_plan,
        approve_revert_plan,
        normalize_realization,
        record_act_on_effect_trace,
        undo_hint_for,
    )
    from plugin.agent.decision_consultation import DecisionOutcome
    from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
    from plugin.agent.executive.meta_consultation import meta_context_packet
    from plugin.agent.executive.sufficiency import DecisionSufficiency
    from plugin.agent.goal import Goal
    from plugin.agent.reflect_diagnosis import seed_reflect_diagnosis_from_measured
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import finalize_surprise_explanation
    from plugin.evals.golden.schema import load_module_cases

    # --- Catalog / aliases (goldens dispatch backtrack|rollback|revert) ---
    if spec_by_name("revert_effects") is None:
        return False, "catalog missing revert_effects"
    if "revert_effects" not in model_allowed_actions():
        return False, "revert_effects not in model_allowed_actions"
    for alias in ("backtrack", "rollback", "revert"):
        if not can_dispatch(alias):
            return False, f"alias {alias!r} not dispatchable → revert_effects"

    # --- Goal + state substrate ---
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    kinds = goal.needed_evidence_kinds()
    if not kinds or (
        "message_bubble" not in kinds and "link" not in kinds and "message" not in kinds
    ):
        return False, f"Goal.needed_evidence_kinds weak: {kinds}"
    state = ExecutionState()
    for attr in (
        "effect_trace",
        "last_branch_fitness",
        "last_branch_consistency",
        "last_selection_consistency",
        "goal_referents",
        "pending_repair_after_revert",
    ):
        if not hasattr(state, attr):
            return False, f"ExecutionState missing {attr}"

    # --- Meta: branch_unfit on context + packet (goldens score via scorer) ---
    if not hasattr(MetaContext, "__dataclass_fields__") or "branch_unfit" not in (
        MetaContext.__dataclass_fields__  # type: ignore[attr-defined]
    ):
        return False, "MetaContext missing branch_unfit"
    pkt = meta_context_packet(
        MetaContext(
            branch_unfit=True,
            branch_fitness={"admissible": False, "reasons": ["gate"], "blockers": []},
            has_grounded_action=False,
        )
    )
    search = pkt.get("search") if isinstance(pkt.get("search"), dict) else {}
    if search.get("branch_unfit") is not True:
        return False, f"meta packet search.branch_unfit missing: {search}"
    if "branch_fitness" not in search:
        return False, "meta packet search.branch_fitness missing"

    # --- Host tags observations; core never needs Videos string list ---
    if not callable(getattr(WhatsAppOverlay, "enrich_world_document", None)):
        return False, "WhatsAppOverlay.enrich_world_document missing"
    tagged = WhatsAppOverlay().enrich_world_document(
        {
            "surface": "search",
            "open_conversation": "• Videos",
            "objects": [{"text": "• Videos", "kind": "chip"}],
        }
    )
    if not any(
        isinstance(o, dict) and o.get("kind") == "filter_chip" for o in (tagged.get("objects") or [])
    ):
        return False, f"overlay did not tag filter_chip: {tagged.get('objects')}"

    # --- Escape unification + undo stack ---
    if normalize_realization("clear_search_filter") != PRESS_ESCAPE:
        return False, "clear_search_filter must normalize to press_escape"
    if normalize_realization("clear_selection_escape") != PRESS_ESCAPE:
        return False, "clear_selection_escape must normalize to press_escape"
    if undo_hint_for(effect_class="blocking_filter") != PRESS_ESCAPE:
        return False, "blocking_filter undo_hint must be press_escape"
    record_act_on_effect_trace(
        state, capability="compose_search_query", target="x", intention={"surface": "search"}
    )
    if not state.effect_trace or not state.effect_trace[-1].get("undo_hint"):
        return False, f"effect_trace missing undo_hint: {state.effect_trace}"

    # --- Behavioral chain goldens need: unfit → scorer BACKTRACK → plan Escape ---
    doc = {
        "surface": "search",
        "objects": [
            {"kind": "filter_chip", "text": "MediaFilter", "restricts": "media"},
            {"kind": "media", "text": "thumb"},
        ],
    }
    fit = compute_branch_fitness(
        doc,
        needed_kinds=kinds,
        goal_referents=["zarooratwala"],
    )
    if fit.get("admissible") is not False:
        return False, f"fitness should be unfit: {fit}"
    choice = select_meta_action(
        MetaContext(
            sufficiency=DecisionSufficiency(
                sufficient_to_act=False,
                observe_has_value=True,
                needs_exploration=True,
                confidence=0.8,
                reason="gate",
            ),
            has_grounded_action=False,
            branch_stale=True,
            branch_unfit=True,
            branch_fitness=fit,
            post_action_look_owed=False,
            information_gathering_exhausted=False,
            backtrack_exhausted=False,
        )
    )
    if choice.action is not MetaAction.EXPLORE:
        return False, f"scorer chose {choice.action} (want EXPLORE) scores={choice.scores}"
    plan = approve_revert_plan(
        analyze_revert_plan(
            document=doc, goal_referents=["zarooratwala"], effect_trace=[], branch_fitness=fit
        ),
        auto=True,
    )
    if not plan.approved or plan.steps[0].realization != PRESS_ESCAPE:
        return False, f"analyze/approve failed: {plan.to_dict()}"

    # --- Reflect + brain consume invoke_revert_effects (ui brain_repair goldens) ---
    packet = {
        "action": {"family": "compose_search_query", "target": "zarooratwala", "executor_ok": True},
        "expected": {"surface": "search"},
        "actual": {"matched": True, "observed_surface": "search", "predicted_surface": "search"},
        "goal": {"link_query": "zarooratwala"},
        "post_world": doc,
        "branch_fitness": fit,
    }
    seed = seed_reflect_diagnosis_from_measured(packet)
    if seed.repair.kind != "invoke_revert_effects" or seed.recommended_next != "explore":
        return False, f"reflect seed={seed.repair.kind}/{seed.recommended_next}"
    expl = finalize_surprise_explanation(
        {"cause": "unknown", "confidence": 0.2, "recommended_next": "reperceive"},
        reflect_packet=packet,
    )
    st = ExecutionState()
    st.perception_mode = "reflect"
    st.last_surprise_explanation = expl
    out = apply_surprise_explanation(
        DecisionOutcome(
            ok=True,
            capability="observe",
            target="",
            why="gate",
            confidence=0.3,
            realization="llm_decision",
        ),
        st,
    )
    if out.capability != "revert_effects":
        return False, f"brain chose {out.capability!r} (want revert_effects)"

    # --- Controller: BACKTRACK dispatches revert_effects; no Videos force-rewrite ---
    ctrl = Path(__file__).resolve().parents[1] / "agent" / "controller.py"
    src = ctrl.read_text(encoding="utf-8")
    if 'name="revert_effects"' not in src and "name='revert_effects'" not in src:
        return False, "controller EXPLORE path missing revert_effects dispatch"
    if "wrong_search_filter" in src and "MetaAction.EXPLORE" in src:
        # Allow comments; forbid the old force-rewrite source tag.
        if 'source": "wrong_search_filter"' in src or "source': 'wrong_search_filter'" in src:
            return False, "controller still force-rewrites meta for wrong_search_filter"

    # --- Recoverability golden corpus present (ui + live-mined meta) ---
    ui_ids = {c.id for c in load_module_cases("ui")}
    required_ui = {
        "ui/live_140713_ocr_videos_grid_reverts_press_escape",
        "ui/live_140713_ocr_videos_seeds_backtrack",
        "ui/live_132831_ocr_two_selected_world",
        "ui/live_132831_ocr_two_selected_reverts",
        "ui/cold_start_filter_chip_reverts_without_trace",
        "ui/live_132831_wrong_selection_seeds_revert",
        "ui/live_145239_correct_selection_still_follows_forward",
    }
    missing_ui = sorted(required_ui - ui_ids)
    if missing_ui:
        return False, f"missing ui goldens: {missing_ui}"
    meta_ids = {c.id for c in load_module_cases("meta_action")}
    if "meta/live_140713_videos_unfit_backtracks_not_ig" not in meta_ids:
        return False, "missing meta/live_140713_videos_unfit_backtracks_not_ig"

    # Spot-score a live-mined ui + meta golden through the real scorers.
    from plugin.evals.golden.score import score_meta_action_case, score_ui_case

    for cid in (
        "ui/live_140713_ocr_videos_grid_reverts_press_escape",
        "ui/live_132831_ocr_two_selected_reverts",
    ):
        case = next(c for c in load_module_cases("ui") if c.id == cid)
        scored = score_ui_case(case)
        if not scored.passed:
            return False, f"ui golden failed under scorer: {cid} {scored.checks}"
    meta_case = next(
        c
        for c in load_module_cases("meta_action")
        if c.id == "meta/live_140713_videos_unfit_backtracks_not_ig"
    )
    scored_m = score_meta_action_case(meta_case)
    if not scored_m.passed:
        return False, f"meta golden failed under scorer: {scored_m.checks}"

    return True, "recoverability substrate wired; live ui/meta goldens score clean"


def _search_results_do_not_observe_thrash() -> Tuple[bool, str]:
    """Live 131221: reveal/observe on search must not thrash — commit unique fit."""
    from plugin.agent.decision_consultation import apply_decision_consultation
    from plugin.agent.features import StateFeatures
    from plugin.agent.goal import Goal
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import UnifiedProposal

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    doc = {
        "surface": "search",
        "objects": [
            {
                "id": "row1",
                "kind": "chat_row",
                "text": "You: https://www.zarooratwala.com/?...",
                "point": [308, 355],
                "matches_goal": True,
            }
        ],
    }

    class _Reveal:
        def choose(self, system: str, packet: dict) -> dict:
            return {
                "capability": "reveal_actions",
                "target": "You: https://www.zarooratwala.com/?...",
                "why": "right-click",
                "confidence": 0.95,
            }

    class _Observe:
        def choose(self, system: str, packet: dict) -> dict:
            return {
                "capability": "observe",
                "target": "",
                "why": "model_requested_observe",
                "confidence": 0.4,
            }

    for chooser, label in ((_Reveal(), "reveal"), (_Observe(), "observe")):
        proposal = UnifiedProposal(
            observed_state={"surface": "search"},
            world_model=dict(doc),
            next_action={},
            confidence=0.9,
        )
        state = ExecutionState()
        state.unified_world_document = dict(doc)
        apply_decision_consultation(
            proposal,
            goal,
            features=StateFeatures(
                extras={"wa_screen": "SEARCH", "search_query": "zarooratwala"}
            ),
            chooser=chooser,
            execution_state=state,
        )
        if proposal.next_action.get("family") != "open_entity":
            return False, f"{label} stayed {proposal.next_action.get('family')!r}"
    return True, "search unique-fit commit after observe/reveal"


def _search_ranks_before_open_on_ambiguous() -> Tuple[bool, str]:
    """Multi-hit search must not commit a query-echo; rank / open content hit."""
    from plugin.agent.capabilities.search_episode import search_continue_capability
    from plugin.agent.decision_consultation import DecisionBrief, TaskState
    from plugin.agent.runtime.state import ExecutionState

    state = ExecutionState()
    brief = DecisionBrief(
        goal={
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
            "destination": "Tanmay",
        },
        world={
            "surface": "search",
            "objects": [
                {
                    "text": "Pallavi: You: zarooratwala Pallavi (Yesterday)",
                    "matches_goal": True,
                },
                {
                    "text": "https://www.zarooratwala.com/fresh",
                    "matches_goal": True,
                },
                {"text": "Zarooratwala Shop", "matches_goal": True},
            ],
        },
        task_state=TaskState(
            phase="reach_source",
            search_query="zarooratwala",
            source_chat_open=False,
        ),
        capabilities=["open_entity", "resolve_entity", "observe"],
    )
    cap, tgt, _why = search_continue_capability(state, brief)
    if cap == "open_entity":
        low = str(tgt or "").lower()
        if "you: zarooratwala" in low:
            return False, f"opened query echo: {tgt!r}"
        if "zarooratwala.com" not in low and "http" not in low:
            return False, f"open target not content-shaped: {tgt!r}"
        return True, "ranked content hit over query echo"
    if cap == "resolve_entity":
        return True, f"deferred commit via {cap}"
    return False, f"unexpected continue {cap!r} target={tgt!r}"


def _entity_resolution_search_owns_meta_and_type_query() -> Tuple[bool, str]:
    """Live 203259: unresolved searchable entity → SEARCH → type_query, not Observe."""
    from plugin.agent.decision_consultation import (
        DecisionBrief,
        DecisionOutcome,
        NavigationInfo,
        TaskState,
        _entity_resolution_type_query_outcome,
    )
    from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice
    from plugin.agent.executive.search_applicability import (
        evaluate_entity_resolution_search,
    )
    from plugin.agent.goal import Goal
    from plugin.agent.runtime.state import ExecutionState

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )

    # Surface lag: perception/last_accepted say forward_picker while doc lags.
    state = ExecutionState()
    state.goal = goal
    state.last_accepted_surface = "forward_picker"
    state.unified_world_document = {
        "surface": "conversation",
        "objects": [
            {"text": "Search", "kind": "search_input", "point": [700, 180]},
            {"text": "Papaji", "kind": "row", "point": [700, 360]},
        ],
        "layers": [{"surface": "forward_picker"}],
    }
    eval_result = evaluate_entity_resolution_search(state)
    if not eval_result.applicable:
        return False, f"lagging surface must still apply SEARCH rule, got {eval_result}"
    if eval_result.gap is None or eval_result.gap.visible_match:
        return False, "Tanmay must be unresolved/not visible"

    # Visible + unselected → ACT select, not SEARCH.
    visible_state = ExecutionState()
    visible_state.goal = goal
    visible_state.unified_world_document = {
        "surface": "forward_picker",
        "objects": [
            {"text": "Search", "kind": "search_input", "point": [700, 180]},
            {"text": "Tanmay", "kind": "row", "point": [700, 400], "selected": False},
        ],
    }
    if evaluate_entity_resolution_search(visible_state).applicable:
        return False, "visible unselected destination must not force SEARCH"

    # Selected → not SEARCH.
    selected_state = ExecutionState()
    selected_state.goal = goal
    selected_state.unified_world_document = {
        "surface": "forward_picker",
        "objects": [
            {
                "text": "Tanmay",
                "kind": "row",
                "selected": True,
                "matches_goal": True,
                "point": [700, 400],
            }
        ],
    }
    if evaluate_entity_resolution_search(selected_state).applicable:
        return False, "selected destination must not force SEARCH"

    # No search facility → EXPLORE path (SEARCH inapplicable).
    barren = ExecutionState()
    barren.goal = goal
    barren.unified_world_document = {
        "surface": "forward_picker",
        "objects": [{"text": "Papaji", "kind": "row", "point": [700, 360]}],
    }
    # Without a search field object, picker still gets a soft opportunity —
    # force absent by using a non-picker scope with no search chrome.
    barren.unified_world_document = {
        "surface": "conversation",
        "objects": [{"text": "Pallavi", "kind": "row", "point": [100, 200]}],
    }
    barren.last_accepted_surface = "conversation"
    if evaluate_entity_resolution_search(barren).applicable:
        return False, "non-picker without search facility must not SEARCH"

    scored = select_meta_action(
        MetaContext(
            destination_search_needed=True,
            act_clear=False,
            has_grounded_action=True,
            post_action_look_owed=True,
            awaiting_verification=True,
            last_action_surprised=False,
            route_discovery_owed=True,
            intention_explore_active=True,
        )
    )
    if scored.action is not MetaAction.SEARCH:
        return False, f"meta must SEARCH over look debt / explore, got {scored}"

    forced = sanitize_meta_choice(
        {"meta_action": "perceive", "why": "look again", "confidence": 0.9},
        MetaContext(
            destination_search_needed=True,
            act_clear=False,
            post_action_look_owed=True,
            last_action_surprised=False,
        ),
    )
    if forced is None or forced.action is not MetaAction.SEARCH:
        return False, f"sanitize must force SEARCH over PERCEIVE, got {forced}"

    brief = DecisionBrief(
        task_state=TaskState(phase="PICK_DEST"),
        world={"surface": "forward_picker", "objects": state.unified_world_document["objects"]},
        navigation=NavigationInfo(surface="forward_picker", forbidden=[]),
        capabilities=["type_query", "resolve_entity", "invoke_affordance", "observe"],
        meta_action="search",
        goal={
            "operation": "whatsapp_forward_message",
            "destination": "Tanmay",
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
        },
    )
    # Ensure evaluation state matches SEARCH brief surface.
    state.unified_world_document = {
        "surface": "forward_picker",
        "objects": [
            {"text": "Search", "kind": "search_input", "point": [700, 180]},
            {"text": "Papaji", "kind": "row", "point": [700, 360]},
        ],
    }
    sealed = _entity_resolution_type_query_outcome(
        brief,
        state,
        prior=DecisionOutcome(
            ok=True,
            capability="observe",
            why="model_requested_observe",
            confidence=0.4,
            realization="decision",
        ),
    )
    if sealed is None or sealed.capability != "type_query":
        return False, f"SEARCH must realize as type_query, got {sealed}"
    if str(sealed.target or "").strip().lower() != "tanmay":
        return False, f"type_query target must be Tanmay, got {sealed.target!r}"
    return True, "entity_resolution_search_owns_meta_and_type_query"


def _source_query_binding_rejects_distractor_urls() -> Tuple[bool, str]:
    """Live 214025: YouTube in Pallavi must not bind/reveal as zarooratwala.

    Invariants:
    1. GoalMatch / scrub: YouTube matches_goal → binding_eligible False.
    2. Object discovery: distractor URL → not_found, no selected id.
    3. Positive: zarooratwala.com remains binding-eligible.
    4. Sanitize: reveal_actions on YouTube rejected while query unpaid.
    5. Meta: address_known + referent_search_needed forces SEARCH not EXPLORE.
    """
    from plugin.agent.decision_consultation import (
        DecisionBrief,
        TaskState,
        sanitize_decision,
    )
    from plugin.agent.executive.meta_action import MetaAction, MetaContext
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice
    from plugin.agent.goal import Goal
    from plugin.agent.object_discovery import resolve_content_rows
    from plugin.agent.source_query_binding import (
        evaluate_source_object_match,
        scrub_matches_goal_flags,
    )

    yt = "https://youtu.be/rHJdc-jkxys?si=M1IrrnzyGF1Jw9wz"
    good = "https://www.zarooratwala.com/fresh"
    gm_bad = evaluate_source_object_match(
        text=yt,
        kind="message_with_link",
        query="zarooratwala",
        container_open="Pallavi",
        expected_container="Pallavi",
        perception_matches_goal=True,
    )
    if gm_bad.binding_eligible or gm_bad.semantic_query_match:
        return False, f"YouTube must not be binding-eligible, got {gm_bad.to_dict()}"
    gm_good = evaluate_source_object_match(
        text=good,
        kind="message_with_link",
        query="zarooratwala",
        container_open="Pallavi",
        expected_container="Pallavi",
        perception_matches_goal=True,
    )
    if not gm_good.binding_eligible or not gm_good.semantic_query_match:
        return False, f"zarooratwala.com must bind, got {gm_good.to_dict()}"

    scrubbed = scrub_matches_goal_flags(
        {
            "open_conversation": "Pallavi",
            "objects": [
                {"id": "yt", "kind": "message_bubble", "text": yt, "matches_goal": True},
                {"id": "zw", "kind": "message_bubble", "text": good, "matches_goal": True},
            ],
        },
        query="zarooratwala",
        expected_container="Pallavi",
    )
    by_id = {o["id"]: o for o in scrubbed["objects"]}
    if by_id["yt"].get("matches_goal"):
        return False, "scrub must clear matches_goal on YouTube"
    if not by_id["zw"].get("matches_goal"):
        return False, "scrub must keep matches_goal on zarooratwala.com"

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    from plugin.agent.object_discovery import DiscoveryContext

    _ctx = DiscoveryContext(use_llm=False, container_id="Pallavi", container_type="conversation")
    resolution = resolve_content_rows(
        goal,
        [
            {
                "entity_id": 88,
                "text": yt,
                "label": yt,
                "object_type": "message_with_link",
            },
            {
                "entity_id": 99,
                "text": "Gate portal today",
                "label": "Gate portal today",
                "object_type": "message",
            },
        ],
        container_id="Pallavi",
        context=_ctx,
    )
    if resolution.status != "not_found" or resolution.selected_source_entity_ids:
        return False, (
            f"discovery must not select YouTube, status={resolution.status} "
            f"ids={resolution.selected_source_entity_ids}"
        )
    resolution_ok = resolve_content_rows(
        goal,
        [
            {
                "entity_id": 88,
                "text": yt,
                "label": yt,
                "object_type": "message_with_link",
            },
            {
                "entity_id": 77,
                "text": good,
                "label": good,
                "object_type": "message_with_link",
            },
        ],
        container_id="Pallavi",
        context=DiscoveryContext(
            use_llm=False, container_id="Pallavi", container_type="conversation"
        ),
    )
    if 77 not in set(resolution_ok.selected_source_entity_ids or []):
        return False, (
            f"discovery must select zarooratwala.com, got "
            f"{resolution_ok.selected_source_entity_ids} status={resolution_ok.status}"
        )

    brief = DecisionBrief(
        goal={
            "operation": "forward_message",
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
            "destination": "Tanmay",
        },
        world={"surface": "conversation", "open_conversation": "Pallavi"},
        capabilities=["reveal_actions", "locate_content", "observe"],
        meta_action="explore",
        task_state=TaskState(
            phase="hunt_content",
            source_chat_open=True,
            content_located=False,
            referent_selected=False,
            referent_binding_status="unresolved",
            selection_consistent=True,
        ),
    )
    rejected = sanitize_decision(
        {
            "capability": "reveal_actions",
            "target": yt,
            "why": "message has a link",
            "confidence": 0.95,
        },
        brief,
    )
    if rejected.ok:
        return False, "reveal_actions on YouTube must fail while source_query unpaid"

    meta = sanitize_meta_choice(
        {"meta_action": "explore", "why": "route discovery", "confidence": 0.9},
        MetaContext(
            address_known=True,
            referent_search_needed=True,
            retrieve_ready=False,
            has_grounded_action=True,
            route_discovery_owed=True,
        ),
    )
    if meta is None or meta.action is not MetaAction.SEARCH:
        return False, f"meta must force SEARCH for unpaid source_object, got {meta}"

    # Live 225807: unified locate_content(YouTube) must rewrite to zarooratwala.
    from plugin.agent.features import StateFeatures
    from plugin.agent.unified_cognition import UnifiedProposal, proposal_to_action
    from plugin.worldmodel.model import WorldModel

    rewritten, reason = proposal_to_action(
        UnifiedProposal(
            observed_state={"surface": "conversation"},
            world_model={"surface": "conversation", "open_conversation": "Pallavi"},
            next_action={
                "family": "locate_content",
                "text": yt,
                "target_label": yt,
                "target_point": [120, 80],
                "coordinate_space": "screen",
                "confidence": 0.95,
            },
            confidence=0.95,
        ),
        goal,
        WorldModel(active_app="WhatsApp"),
        StateFeatures(),
    )
    if rewritten is None:
        return False, f"locate_content rewrite failed: {reason}"
    got_q = str(getattr(rewritten, "text", "") or "")
    if "zarooratwala" not in got_q.lower() or "youtu" in got_q.lower():
        return False, f"locate must use zarooratwala not YouTube, got {got_q!r}"

    return True, "source_query_binding_rejects_distractor_urls"


def _typed_role_binding_identity_gates() -> Tuple[bool, str]:
    """Relevance ≠ binding via policy + evidence providers + generic resolver.

    Core must not contain WhatsApp row/preview extraction. Domain adapters emit
    identity_evidence vs content_evidence. Cross-domain: thread/folder/tab.
    """
    import inspect

    from plugin.agent.decision_consultation import (
        DecisionBrief,
        TaskState,
        sanitize_decision,
    )
    from plugin.agent.executive.meta_action import MetaAction, MetaContext
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice
    from plugin.agent.composition import compose_domain_adapters
    from plugin.agent.procedures.forward_message import forward_role_specs
    from plugin.agent.role_binding import (
        BindingRecord,
        EntityObservation,
        IdentityEvidence,
        RoleBinder,
        assess_candidate_for_role,
        assess_observation_for_role,
        record_negative_evidence,
    )
    import plugin.agent.role_binding as rb_mod

    compose_domain_adapters()
    src = inspect.getsource(rb_mod)
    for banned in (
        "_row_contact_name",
        "extract_contact_name",
        "whatsapp_view",
        "open_matches_referent",
        "source_query_binding",
    ):
        if banned in src:
            return False, f"core role_binding still contains {banned!r}"

    class _Goal:
        contact = "Pallavi"
        link_query = "zarooratwala"
        target_contact = "Tanmay"

    specs = forward_role_specs(_Goal())
    # Typed evidence: preview is content, not identity.
    typed = EntityObservation(
        entity_kind="conversation",
        label="Pallavi",
        identity_evidence=[IdentityEvidence(kind="display_name", value="Pallavi")],
        content_evidence=[
            IdentityEvidence(
                kind="preview_text",
                value="https://youtu.be/x",
                identity_bearing=False,
            )
        ],
    )
    if not assess_observation_for_role(
        spec=specs["source_container"], observation=typed, goal=_Goal()
    ).binding_eligible:
        return False, "typed conversation+preview must bind container"
    # WhatsApp adapter path (domain extraction stays out of core).
    a = assess_candidate_for_role(
        spec=specs["source_container"],
        candidate={
            "label": "Pallavi - You: https://youtu.be/rHJdc-jkxys",
            "kind": "chat_row",
            "domain": "whatsapp",
        },
        goal=_Goal(),
        task_relevance=0.4,
    )
    if not a.binding_eligible:
        return False, f"A: adapter-split Pallavi+YouTube must bind container, {a.to_dict()}"

    b = assess_candidate_for_role(
        spec=specs["source_container"],
        candidate={
            "label": "ZarooratWala – Fresh Groceries Delivery",
            "kind": "search_result_row",
            "domain": "whatsapp",
            "text": "zarooratwala.com",
        },
        goal=_Goal(),
        task_relevance=0.99,
    )
    if b.binding_eligible:
        return False, f"B: brand row must fail container identity, got {b.to_dict()}"

    msg = {
        "label": "https://www.zarooratwala.com/fresh",
        "text": "https://www.zarooratwala.com/fresh",
        "kind": "message_with_link",
        "domain": "whatsapp",
        "container": "Pallavi",
    }
    if assess_candidate_for_role(
        spec=specs["source_object"], candidate=msg, goal=_Goal(), bindings={}
    ).binding_eligible:
        return False, "C: source_object must wait for container binding"
    if not assess_candidate_for_role(
        spec=specs["source_object"],
        candidate=msg,
        goal=_Goal(),
        bindings={"source_container": {"resolved_label": "Pallavi"}},
    ).binding_eligible:
        return False, "C: zarooratwala message must bind after container"

    # Cross-domain: folder identity ≠ child filename.
    class FolderGoal:
        contact = "Specs"
        link_query = "charger"
        target_contact = "X"

    folder = EntityObservation(
        entity_kind="container",
        identity_evidence=[IdentityEvidence(kind="directory_name", value="Specs")],
        content_evidence=[
            IdentityEvidence(
                kind="filename", value="charger.pdf", identity_bearing=False
            )
        ],
    )
    if not assess_observation_for_role(
        spec=forward_role_specs(FolderGoal())["source_container"],
        observation=folder,
        goal=FolderGoal(),
    ).binding_eligible:
        return False, "folder directory_name must bind container"
    if assess_observation_for_role(
        spec=forward_role_specs(FolderGoal())["source_object"],
        observation=folder,
        goal=FolderGoal(),
        bindings={"source_container": {"resolved_label": "Specs"}},
        task_relevance=0.99,
    ).binding_eligible:
        return False, "folder must not bind as source_object via child filename"

    # ACT consumes binding — does not re-score identity.
    ok, why, _ = RoleBinder().action_allowed(
        role="source_container",
        target="Pallavi",
        binding=BindingRecord(
            role="source_container",
            label="Pallavi",
            entity_id="1",
            status="confirmed",
        ),
        allow_propose=False,
    )
    if not ok or why != "binding_valid":
        return False, f"ACT must consume valid binding, got {ok}/{why}"

    brief = DecisionBrief(
        goal={
            "contact": "Pallavi",
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
            "destination": "Tanmay",
        },
        capabilities=["open_entity", "resolve_entity"],
        meta_action="act",
        candidates=["ZarooratWala – Fresh Groceries Delivery", "Pallavi"],
        task_state=TaskState(
            phase="reach_source", search_query="Pallavi zarooratwala"
        ),
    )
    if sanitize_decision(
        {
            "capability": "open_entity",
            "target": "ZarooratWala – Fresh Groceries Delivery",
            "why": "matches query",
            "confidence": 0.99,
        },
        brief,
    ).ok:
        return False, "sanitize must reject brand row as source_container open"

    class ES:
        binding_negative_evidence = None
        last_effect_closure = {}

    es = ES()
    record_negative_evidence(
        es, role="source_container", candidate_label="ZarooratWala – Fresh"
    )
    if not es.last_effect_closure.get("referent_search_needed"):
        return False, "REFERENT_MISMATCH must arm referent_search_needed"
    if es.last_effect_closure.get("referent_repair_owed"):
        return False, "container REFERENT_MISMATCH must not arm ACT repair"

    meta = sanitize_meta_choice(
        {"meta_action": "act", "why": "retry", "confidence": 0.9},
        MetaContext(role_identity_search_owed=True, has_grounded_action=True),
    )
    if meta is None or meta.action is not MetaAction.SEARCH:
        return False, f"meta must SEARCH on role identity mismatch, got {meta}"

    return True, "typed_role_binding_identity_gates"


def _coordinate_frame_roundtrip_and_typed_actuators() -> Tuple[bool, str]:
    """Trustworthy chain: frames, coverage split, chord≠click, attempt validity."""
    from plugin.agent.capabilities.invoke_affordance import invoke_affordance
    from plugin.agent.executive.intention_frame import (
        AttemptValidity,
        MethodOutcome,
        MethodStatus,
        MethodFrontier,
        MethodSpec,
        begin_attempt,
        close_attempt,
        mark_method_attempted,
        record_method_status,
    )
    from plugin.agent.failure_layers import filter_capability_failure_beliefs
    from plugin.perception.coordinate_frame import (
        GroundingUncertain,
        UnknownCoordinateFrame,
        build_frame_graph,
        ensure_screen_space,
        roundtrip_error_px,
    )
    from plugin.perception.coverage_quality import (
        ActSufficiency,
        compute_coverage_quality,
    )
    from plugin.worldmodel.scene.focus import _surface_state_from_view

    for pt, size, origin, pscale, cscale in (
        ((120.0, 80.0), (1440.0, 900.0), (0.0, 0.0), 1.0, 1.0),
        ((900.0, 240.0), (1581.0, 979.0), (774.0, 25.0), 1.0 / 1.4328125, 1.4328125),
        ((40.0, 200.0), (1200.0, 800.0), (100.0, 50.0), 1.0, 1.0),
        ((300.0, 300.0), (800.0, 600.0), (200.0, 100.0), 1.0, 1.0),
    ):
        err = roundtrip_error_px(
            pt,
            image_size=size,
            window_origin=origin,
            point_scale=pscale,
            capture_scale=cscale,
        )
        if err >= 3.0:
            return False, f"roundtrip err={err} for {pt}"

    # Capture ≠ window: ROI image_origin distinct from window origin.
    g = build_frame_graph(
        image_size=(400.0, 300.0),
        window_origin_in_screen=(100.0, 50.0),
        image_origin_in_window=(40.0, 20.0),
        point_scale=1.0,
        capture_id="c_gate",
    )
    img = g.get(g.image_frame_id)
    if img is None or img.image_origin_in_window != (40.0, 20.0):
        return False, "image_origin_in_window must be distinct from window origin"
    if img.window_origin_in_screen != (100.0, 50.0):
        return False, "window_origin_in_screen collapsed into image origin"

    pt, _, audit = ensure_screen_space(
        (450.0, 230.0),
        None,
        coordinate_space="screen",
        graph=g,
    )
    if pt != (450.0, 230.0) or not audit.get("double_transform_refused"):
        return False, "screen-tagged point must refuse double-transform"

    try:
        ensure_screen_space((1.0, 2.0), None, coordinate_space="", fail_closed=True)
        return False, "missing frame must fail closed"
    except (GroundingUncertain, UnknownCoordinateFrame):
        pass

    q = compute_coverage_quality(
        nodes=[{"role": "AXApplication"}, {"role": "AXWindow"}, {"role": "unknown"}],
        has_screenshot=True,
    )
    if q.task_coverage >= 0.5 or not q.chrome_only:
        return False, f"chrome-only AX must not look task-covered: {q.to_dict()}"
    if ActSufficiency().satisfied(q):
        return False, "ActSufficiency must reject chrome-only"

    # AXGroup with labeled child is not chrome.
    q2 = compute_coverage_quality(
        nodes=[
            {
                "role": "AXGroup",
                "children": [{"role": "AXStaticText", "label": "Hello"}],
            }
        ],
        has_screenshot=True,
        semantic_object_count=1,
    )
    if q2.chrome_only:
        return False, "AXGroup with content must not be chrome_only"

    st = _surface_state_from_view(
        {
            "screen": "LIST",
            "window_name": "WhatsApp for Mac",
            "visible_contacts": ["A"],
            "open_conversation": "",
            "empty_placeholder": True,
        },
        "reach_source",
    )
    if st.main_surface != "empty_placeholder":
        return False, f"list+placeholder mislabelled: {st.to_dict()}"

    class _RT:
        def activate(self, app):
            pass

        def click(self, app, label, *, bounds=None):
            raise AssertionError("chord must not click")

    out = invoke_affordance("WhatsApp", "press_cmd_shift_f", _RT())
    if out.ok or out.realization == "named_click":
        return False, f"chord must not named_click: {out.realization}"

    att = begin_attempt(method_id="reveal_context_click")
    close_attempt(
        att,
        method_outcome=MethodOutcome.EFFECT_ABSENT.value,
        attempt_validity=AttemptValidity.INCONCLUSIVE_GROUNDING.value,
    )
    if att.may_mark_method_ineffective() or att.method_status != MethodStatus.UNTRIED.value:
        return False, "inconclusive grounding must not exhaust method"

    # Attempt ledger ≠ eligibility: inconclusive leave method eligible.
    from plugin.agent.executive.intention_frame import Intention, IntentionFrame

    frame = IntentionFrame(
        intention=Intention(id="i_gate", objective="x", success_predicate="x")
    )
    frame.method_frontier = MethodFrontier(
        known_untried=["reveal_context_click"],
        catalog={
            "reveal_context_click": MethodSpec(
                id="reveal_context_click", capability="reveal_actions"
            )
        },
    )
    mark_method_attempted(frame, "reveal_context_click")
    record_method_status(frame, "reveal_context_click", MethodStatus.UNTRIED.value)
    if "reveal_context_click" not in frame.method_frontier.eligible_methods():
        return False, "inconclusive attempt must leave method eligible"

    class ES:
        attempt_validity = "inconclusive_grounding"

    kept = filter_capability_failure_beliefs(
        ["mouse_interaction_blocked"],
        execution_state=ES(),
        evidence={"intended_vs_landed_distance_px": 783},
    )
    if kept:
        return False, "must strip mouse_interaction_blocked under uncertain grounding"

    return True, "coordinate_frame_roundtrip_and_typed_actuators"


def _core_generalization_gate() -> Tuple[bool, str]:
    """Generic executive/binder/grounder must not import domain workflows."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "agent"
    forbidden_imports = {
        "whatsapp",
        "gmail",
        "finder",
        "pallavi",
        "zarooratwala",
    }
    # Modules that must stay domain-free.
    core_files = [
        root / "role_binding.py",
        root / "executive" / "intention_frame.py",
        root / "failure_layers.py",
        Path(__file__).resolve().parents[1] / "perception" / "coordinate_frame.py",
    ]
    bad: List[str] = []
    for path in core_files:
        if not path.is_file():
            continue
        src = path.read_text(encoding="utf-8")
        low = src.lower()
        for token in forbidden_imports:
            if token == "whatsapp" and path.name == "role_binding.py":
                # role_binding must not import whatsapp at all.
                if "identity_evidence.whatsapp" in low or "ensure_whatsapp" in low:
                    bad.append(f"{path.name}:whatsapp_import")
                continue
            if token in low and path.name in {
                "role_binding.py",
                "intention_frame.py",
                "failure_layers.py",
                "coordinate_frame.py",
            }:
                # Allow comments mentioning examples only if not import lines.
                try:
                    tree = ast.parse(src)
                except SyntaxError:
                    bad.append(f"{path.name}:parse")
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        mod = ""
                        if isinstance(node, ast.ImportFrom):
                            mod = str(node.module or "")
                        else:
                            mod = ",".join(a.name for a in node.names)
                        if token in mod.lower():
                            bad.append(f"{path.name}:import:{token}")
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        continue
    if bad:
        return False, f"core_generalization violations: {bad[:8]}"
    return True, "core_generalization_gate"


def _typed_action_and_untyped_geometry_gate() -> Tuple[bool, str]:
    """Production act path refuses free-text chords as clicks and untyped XY."""
    from plugin.agent.actor import _normalize_to_screen
    from plugin.agent.capabilities.invoke_affordance import invoke_affordance
    from plugin.agent.capabilities.typed_actuators import KeyboardChord
    from plugin.perception.coordinate_frame import build_frame_graph

    class _RT:
        def activate(self, app):
            pass

        def click(self, app, label, *, bounds=None):
            raise AssertionError("must not click")

    out = invoke_affordance("App", "press_cmd_shift_f", _RT())
    if out.realization == "named_click" or out.ok:
        return False, "free-text chord must not become click"

    # Typed chord schema exists.
    chord = KeyboardChord(keys=("command", "shift", "f"), provenance="observed")
    if "keyboard_chord" not in chord.to_dict().get("kind", ""):
        return False, "KeyboardChord schema missing"

    # Stale/unknown frame_id must fail closed (no space/screen guess).
    graph_tmp = build_frame_graph(
        image_size=(100.0, 100.0),
        window_origin_in_screen=(5.0, 5.0),
        capture_id="c_stale",
    )
    pt, bd, audit = _normalize_to_screen(
        (10.0, 20.0),
        None,
        coordinate_space="image",
        surface=None,
        frame_id="capture:other/image",
        graph=graph_tmp,
    )
    if pt is not None or not audit.get("grounding_uncertain"):
        return False, f"stale frame_id must fail closed: pt={pt} audit={audit}"

    # Naked [x,y] with no frame/space must fail closed in production.
    naked_pt, _, naked_audit = _normalize_to_screen(
        (450.0, 230.0),
        None,
        coordinate_space="",
        surface=None,
        frame_id="",
        graph=None,
        allow_legacy_geometry=False,
    )
    if naked_pt is not None or not naked_audit.get("grounding_uncertain"):
        return False, f"naked geometry must fail closed: pt={naked_pt} audit={naked_audit}"

    # Image geometry without FrameGraph must fail closed (no legacy_identity).
    img_pt, _, img_audit = _normalize_to_screen(
        (450.0, 230.0),
        None,
        coordinate_space="image",
        surface=None,
        frame_id="",
        graph=None,
        allow_legacy_geometry=False,
    )
    if img_pt is not None or not img_audit.get("grounding_uncertain"):
        return False, f"image without FrameGraph must fail closed: {img_pt} {img_audit}"

    # Cross-capture grounding must fail closed (zero motor coordinates emitted).
    graph_b = build_frame_graph(
        image_size=(100.0, 100.0),
        window_origin_in_screen=(0.0, 0.0),
        capture_id="c_B",
    )
    stale_pt, _, stale_audit = _normalize_to_screen(
        (10.0, 20.0),
        None,
        coordinate_space="image",
        surface=None,
        frame_id=graph_b.image_frame_id,
        graph=graph_b,
        grounding_capture_id="c_A",
    )
    if stale_pt is not None or not stale_audit.get("grounding_uncertain"):
        return False, f"stale capture must fail closed: pt={stale_pt} audit={stale_audit}"

    graph = build_frame_graph(
        image_size=(100.0, 100.0),
        window_origin_in_screen=(0.0, 0.0),
        capture_id="c_typed",
    )
    pt2, _, audit2 = _normalize_to_screen(
        (10.0, 20.0),
        None,
        coordinate_space="image",
        surface=None,
        frame_id=graph.image_frame_id,
        graph=graph,
        grounding_capture_id="c_typed",
    )
    if pt2 is None or audit2.get("grounding_uncertain"):
        return False, f"grounded image point must transform: {pt2} {audit2}"

    # typed_actuators must stay dependency-clean (no legacy re-exports).
    import ast
    import inspect
    from plugin.agent.capabilities import typed_actuators as ta_mod

    ta_src = inspect.getsource(ta_mod)
    if "def looks_like_keyboard_chord" in ta_src or "def parse_keyboard_chord" in ta_src:
        return False, "typed_actuators must not re-export legacy chord parsers"
    try:
        tree = ast.parse(ta_src)
    except SyntaxError:
        return False, "typed_actuators parse failed"
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and "legacy_action_adapter" in str(
            node.module or ""
        ):
            return False, "typed_actuators must not import legacy_action_adapter"

    # Production callers must not grow new role_binding forward shims.
    from pathlib import Path

    agent_root = Path(__file__).resolve().parents[1] / "agent"
    shim_callers = ("controller.py", "decision_consultation.py")
    for name in shim_callers:
        src = (agent_root / name).read_text(encoding="utf-8")
        if "from plugin.agent.role_binding import" in src and "role_for_action_family" in src:
            # Allow only if role_for_action_family is not imported from role_binding.
            import ast

            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "plugin.agent.role_binding":
                    for alias in node.names:
                        if alias.name == "role_for_action_family":
                            return False, f"{name} still imports role_for_action_family shim"
                        if alias.name == "forward_role_specs":
                            return False, f"{name} still imports forward_role_specs shim"

    return True, "typed_action_and_untyped_geometry_gate"


def _search_evidence_owns_surface_and_resolve_recovery() -> Tuple[bool, str]:
    """Live 210526: contradicted conversation patch + resolve≠open + decline→open.

    Three coupled invariants:
    1. resolve_entity / compose must not stamp conversation_open as act intention.
    2. Critic must reject conversation when prediction_error/observed say search.
    3. After search episode complete on search_results, unified decline opens
       the chosen entity instead of Observe thrash.
    """
    from plugin.agent.action import Action
    from plugin.agent.decision import DecisionEngine
    from plugin.agent.features import StateFeatures
    from plugin.agent.goal import Goal
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import (
        intention_expectation_from_decision,
        proposal_to_action,
        UnifiedProposal,
    )
    from plugin.agent.world_critic import critique_world_proposal
    from plugin.worldmodel.model import WorldModel

    # (1) Family contract beats look wish for conversation.
    for fam in ("resolve_entity", "compose_search_query", "type_query"):
        claim = intention_expectation_from_decision(
            Action(
                action=fam,
                action_family=fam,
                semantic_target="Pallavi",
                prediction={
                    "expected_surface": "conversation",
                    "expected_affordances": [
                        "message_bubbles",
                        "input_field",
                        "header_info",
                    ],
                },
                expected_predicate="conversation",
            )
        )
        if claim.get("surface") != "search":
            return False, f"{fam} intention surface={claim.get('surface')!r} want search"
        if "message_bubbles" in [str(c).lower() for c in (claim.get("likely_controls") or [])]:
            return False, f"{fam} still claims conversation chrome"

    proposal = UnifiedProposal(
        observed_state={"surface": "search"},
        world_model={"surface": "search", "objects": []},
        next_action={
            "family": "resolve_entity",
            "text": "Pallavi",
            "target_label": "Pallavi",
            "target_point": [300, 400],
            "coordinate_space": "screen",
            "confidence": 0.95,
        },
        expected_transition={
            "surface": "conversation",
            "likely_controls": ["message_bubbles", "input_field", "header_info"],
        },
        confidence=0.95,
    )
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    action, reason = proposal_to_action(
        proposal, goal, WorldModel(active_app="WhatsApp"), StateFeatures()
    )
    if action is None:
        return False, f"proposal_to_action failed: {reason}"
    pred = dict(action.prediction or {})
    if str(pred.get("expected_surface") or "") != "search":
        return False, f"resolve_entity prediction surface={pred.get('expected_surface')!r}"
    if pred.get("claims_navigation") is not False:
        return False, "resolve_entity must set claims_navigation=False"

    # (2) Critic authority: prediction_error alters belief.
    verdict = critique_world_proposal(
        {"surface": "search", "open_conversation": "", "search_query": "zarooratwala Pallavi"},
        {
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "search_query": "zarooratwala Pallavi",
            "objects": [
                {
                    "id": "links",
                    "kind": "filter_chip",
                    "text": "Links",
                    "restricts": "result_scope",
                },
                {
                    "id": "messages",
                    "kind": "filter_chip",
                    "text": "Messages",
                    "restricts": "result_scope",
                },
            ],
        },
        last_action="resolve_entity",
        observed_surface="search",
        prediction_error={
            "predicted_surface": "conversation",
            "observed_surface": "search",
            "matched": False,
        },
    )
    if verdict.accepted_document.get("surface") != "search":
        return False, (
            f"critic accepted surface={verdict.accepted_document.get('surface')!r} "
            "despite search evidence"
        )
    if verdict.accepted_document.get("open_conversation"):
        return False, "critic must clear open_conversation under search evidence"

    # (3) Decline recovery → open_entity, not Observe.
    state = ExecutionState()
    state.goal = goal
    state.last_meta_action = "act"
    state.search_episode = {
        "status": "complete",
        "chosen_label": "Pallavi: https://www.zarooratwala.com/?",
        "referent": "Pallavi",
        "query": "zarooratwala Pallavi",
    }
    state.unified_world_document = {
        "surface": "search",
        "open_conversation": "",
        "search_query": "zarooratwala Pallavi",
        "objects": [
            {
                "id": "row",
                "kind": "chat_row",
                "text": "Pallavi: https://www.zarooratwala.com/?",
                "matches_goal": True,
                "point": [300, 400],
            }
        ],
        "primary_surface": "search_results",
    }
    engine = DecisionEngine()
    recovered = engine._observe_when_unified_declines(
        StateFeatures(extras={"wa_screen": "SEARCH_RESULTS", "screen_bucket": "search"}),
        state,
        goal,
    )
    if str(getattr(recovered, "action_family", "") or "") != "open_entity":
        return False, (
            f"decline recovery family={getattr(recovered, 'action_family', None)!r} "
            f"rationale={getattr(recovered, 'rationale', None)!r}"
        )
    return True, "search_evidence_owns_surface_and_resolve_recovery"


def _stale_compose_search_does_not_arm_retreat() -> Tuple[bool, str]:
    """Live 202457: Chrome foreground refuse must not mark search retreat_owed."""
    from plugin.agent.capabilities.search_episode import (
        note_find_stage_outcome,
        search_episode_of,
        start_search_episode,
    )
    from plugin.agent.executive.meta_action import MetaAction, MetaContext
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice
    from plugin.agent.runtime.state import ExecutionState

    state = ExecutionState()
    start_search_episode(
        state,
        role="source",
        referent="Pallavi",
        query="",
        status="querying",
        reason="compose_pending",
    )
    note_find_stage_outcome(
        state,
        family="compose_search_query",
        ok=False,
        message=(
            "perception_invalid: refused stale click on 'Search': "
            "'Google Chrome' holds the foreground, not 'WhatsApp'"
        ),
    )
    if bool(getattr(state, "search_retreat_owed", False)):
        return False, "stale compose_search armed search_retreat_owed"
    ep = search_episode_of(state) or {}
    if str(ep.get("status") or "") == "failed":
        return False, f"stale refuse left episode failed: {ep}"
    # SEARCH must remain admissible after reclaim (not forced to EXPLORE).
    choice = sanitize_meta_choice(
        {"meta_action": "search", "why": "retry compose after reclaim", "confidence": 0.9},
        MetaContext(
            referent_search_needed=True,
            search_episode_failed=False,
            search_retreat_owed=bool(getattr(state, "search_retreat_owed", False)),
            search_has_criteria=True,
        ),
    )
    if choice is None or choice.action is not MetaAction.SEARCH:
        return False, f"expected SEARCH admissible after stale refuse, got {choice}"
    return True, "stale_compose_search_does_not_arm_retreat"


def _find_outcome_seam_never_leaves_ranking() -> Tuple[bool, str]:
    """Live 213012: resolve abstain / latch must not leave episode ranking for re-SEARCH."""
    from plugin.agent.actor import CAPABILITY_GESTURE
    from plugin.agent.capabilities.search_episode import (
        note_find_stage_outcome,
        search_continue_capability,
        search_episode_of,
        start_search_episode,
    )
    from plugin.agent.decision_consultation import DecisionBrief, TaskState
    from plugin.agent.executive.meta_action import MetaAction, MetaContext
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice
    from plugin.agent.runtime.state import ExecutionState

    if "resolve_entity" in CAPABILITY_GESTURE:
        return False, "resolve_entity must not map to a motor gesture"

    state = ExecutionState()
    start_search_episode(
        state,
        role="source",
        referent="Pallavi",
        query="zarooratwala",
        status="ranking",
        reason="gate",
    )
    note_find_stage_outcome(
        state,
        family="resolve_entity",
        ok=False,
        message="resolve_no_match",
    )
    ep = search_episode_of(state) or {}
    if str(ep.get("status") or "") != "failed":
        return False, f"abstain left status={ep.get('status')!r}"
    if not bool(getattr(state, "search_retreat_owed", False)):
        return False, "abstain must set search_retreat_owed"

    retreat = sanitize_meta_choice(
        {"meta_action": "search", "why": "retry find", "confidence": 0.9},
        MetaContext(
            referent_search_needed=True,
            search_episode_failed=True,
            search_retreat_owed=True,
        ),
    )
    if retreat is None or retreat.action is not MetaAction.EXPLORE:
        return False, f"retreat sanitize expected EXPLORE, got {retreat}"

    # Chosen under SEARCH → complete; continue does not open (ACT opens next).
    chosen_state = ExecutionState()
    start_search_episode(
        chosen_state,
        role="source",
        referent="Pallavi",
        query="zarooratwala",
        status="ranking",
        reason="gate",
    )
    from plugin.agent.capabilities.search_episode import complete_search_choice

    complete_search_choice(chosen_state, chosen_label="Pallavi")
    note_find_stage_outcome(
        chosen_state,
        family="resolve_entity",
        ok=True,
        message="chosen",
    )
    ep2 = search_episode_of(chosen_state) or {}
    if str(ep2.get("status") or "") != "complete":
        return False, f"chosen left status={ep2.get('status')!r}"
    brief = DecisionBrief(
        goal={"source_conversation": "Pallavi", "destination": "Tanmay"},
        world={"surface": "search", "objects": [{"text": "Pallavi", "kind": "chat_row"}]},
        task_state=TaskState(phase="reach_source", search_query="zarooratwala"),
        capabilities=["open_entity", "resolve_entity", "observe"],
        meta_action="search",
        search_episode=ep2,
    )
    cap, _tgt, why = search_continue_capability(chosen_state, brief)
    if cap:
        return False, f"under SEARCH meta after complete, continue={cap!r} ({why})"
    # Open miss after complete must not fail the episode / re-arm SEARCH.
    note_find_stage_outcome(
        chosen_state,
        family="open_entity",
        ok=False,
        message="AX element not found",
    )
    ep3 = search_episode_of(chosen_state) or {}
    if str(ep3.get("status") or "") != "complete":
        return False, f"open miss must keep complete, got {ep3.get('status')!r}"
    if bool(getattr(chosen_state, "search_retreat_owed", False)):
        return False, "open miss must not set search_retreat_owed"
    return True, "find outcome seam: abstain retreats; chosen completes; open miss stays ACT"


def _meta_search_owns_find_among_many() -> Tuple[bool, str]:
    """Referent find is MetaAction.SEARCH; ACT while incomplete rewrites to SEARCH."""
    from plugin.agent.capabilities.catalog import model_allowed_actions, spec_by_name
    from plugin.agent.executive.meta_action import MetaAction, MetaContext, MetaChoice
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice

    if MetaAction.SEARCH.value != "search":
        return False, "MetaAction.SEARCH missing"
    if not MetaChoice(MetaAction.SEARCH, "x").may_actuate:
        return False, "SEARCH must may_actuate find stages"
    if MetaChoice(MetaAction.THINK, "x").may_actuate:
        return False, "THINK must not actuate UI find"
    spec = spec_by_name("search")
    if spec is None:
        return False, "catalog missing search contract entry"
    if str(getattr(spec.status, "value", spec.status)) == "realized":
        if "search" in model_allowed_actions():
            return False, "compound search must not be an ACT brain verb"
    ctx = MetaContext(
        referent_search_needed=True,
        search_episode_incomplete=True,
        search_episode_complete=False,
    )
    choice = sanitize_meta_choice(
        {"meta_action": "act", "why": "open", "confidence": 0.9}, ctx
    )
    if choice is None or choice.action is not MetaAction.SEARCH:
        return False, f"ACT while search owed → {getattr(choice, 'action', None)}"
    done = MetaContext(search_episode_complete=True, has_grounded_action=True)
    choice2 = sanitize_meta_choice(
        {"meta_action": "act", "why": "open chosen", "confidence": 0.9}, done
    )
    if choice2 is None or choice2.action is not MetaAction.ACT:
        return False, "ACT after search complete must remain ACT"
    # GoalState (workspace) must arm referent_search.needed — live 165649
    # had empty execution_state.goal so ACT+compose slipped through.
    from plugin.agent.capabilities.search_episode import meta_referent_search_signals
    from plugin.agent.executive.workspace import GoalState
    from plugin.agent.runtime.state import ExecutionState

    sig = meta_referent_search_signals(
        ExecutionState(),
        phase="reach_source",
        source_chat_open=False,
        surface="chat_list",
        goal=GoalState(subject="Pallavi", query="zarooratwala", destination="Tanmay"),
    )
    if not sig.get("needed"):
        return False, "GoalState subject/query must set referent_search.needed"
    # Identity ≠ membership; unpaid content still owes SEARCH (live 214626).
    from plugin.agent.capabilities.resolve_entity import open_matches_referent

    if open_matches_referent("Pallavi, Papaji, Rekha, You", "Pallavi"):
        return False, "participant CSV must not match source identity"
    content_owed = meta_referent_search_signals(
        ExecutionState(),
        phase="hunt_content",
        source_chat_open=True,
        surface="conversation",
        goal=GoalState(subject="Pallavi", query="zarooratwala", destination="Tanmay"),
        content_located=False,
    )
    if not content_owed.get("needed"):
        return False, "unpaid link_query must keep referent_search.needed after source open"
    # Empty find → retreat before re-SEARCH (loop convergence; no host catalog).
    retreat_ctx = MetaContext(
        referent_search_needed=True,
        search_episode_failed=True,
        search_retreat_owed=True,
    )
    retreat = sanitize_meta_choice(
        {"meta_action": "search", "why": "retry", "confidence": 0.9}, retreat_ctx
    )
    if retreat is None or retreat.action is not MetaAction.EXPLORE:
        return False, f"failed search must rewrite SEARCH→EXPLORE, got {retreat}"
    # SearchIntent / SearchResult contract on episode + meta packet fields.
    from plugin.agent.capabilities.search_episode import (
        SearchIntent,
        SearchResult,
        fail_search_episode,
        search_intent_from_episode,
        search_result_from_episode,
        start_search_episode,
    )
    from plugin.agent.executive.meta_consultation import meta_context_packet
    from plugin.agent.runtime.state import ExecutionState as _ES

    st = _ES()
    start_search_episode(
        st, referent="Pallavi", query="zarooratwala Pallavi", space="ui_filter"
    )
    ep0 = getattr(st, "search_episode", None) or {}
    intent = search_intent_from_episode(ep0)
    if not isinstance(intent, SearchIntent) or not intent.sought:
        return False, f"SearchIntent missing sought from episode: {intent}"
    if "intent" not in ep0 or "result" not in ep0:
        return False, "episode must stamp intent/result contract"
    fail_search_episode(st, reason="empty_candidate_set")
    result = search_result_from_episode(getattr(st, "search_episode", None), exhausted=True)
    if not isinstance(result, SearchResult):
        return False, "SearchResult type missing"
    if not result.exhausted:
        return False, "failed find must mark SearchResult.exhausted"
    if not result.unexplored_scopes:
        return False, "SearchResult must expose unexplored_scopes after partial/empty find"
    if not isinstance(result.coverage, dict) or "explored_scopes" not in result.coverage:
        return False, f"SearchResult.coverage incomplete: {result.coverage}"
    # SEARCH without criteria → EXPLORE
    no_crit = sanitize_meta_choice(
        {"meta_action": "search", "why": "how do I Forward?", "confidence": 0.8},
        MetaContext(search_has_criteria=False),
    )
    if no_crit is None or no_crit.action is not MetaAction.EXPLORE:
        return False, f"SEARCH without criteria must → EXPLORE, got {no_crit}"
    # EXPLORE exists; legacy probe token must not parse; compose forbidden under explore.
    if MetaAction.EXPLORE.value != "explore":
        return False, "MetaAction.EXPLORE missing"
    if not MetaChoice(MetaAction.EXPLORE, "x").may_actuate:
        return False, "EXPLORE must may_actuate reveal stages"
    from plugin.agent.executive.meta_consultation import _parse_action

    if _parse_action({"meta_action": "probe"}) is not None:
        return False, "legacy probe token must not parse"
    explore_ok = sanitize_meta_choice(
        {"meta_action": "explore", "why": "reveal", "confidence": 0.8},
        MetaContext(),
    )
    if explore_ok is None or explore_ok.action is not MetaAction.EXPLORE:
        return False, f"explore must parse, got {explore_ok}"
    from plugin.agent.decision_consultation import (
        DecisionBrief,
        TaskState,
        sanitize_decision,
    )

    explore_brief = DecisionBrief(
        goal={"source_conversation": "Pallavi"},
        world={"surface": "conversation", "objects": []},
        task_state=TaskState(phase="act_on_content"),
        capabilities=[
            "reveal_actions",
            "observe",
            "compose_search_query",
            "resolve_entity",
        ],
        meta_action="explore",
    )
    compose_rej = sanitize_decision(
        {"capability": "compose_search_query", "target": "x", "why": "type"},
        explore_brief,
    )
    if compose_rej.ok:
        return False, "EXPLORE meta must forbid compose_search_query"
    # Address known → RETRIEVE/ACT, not SEARCH (unless route discovery owed)
    retrieve = sanitize_meta_choice(
        {"meta_action": "search", "why": "find again", "confidence": 0.8},
        MetaContext(retrieve_ready=True, address_known=True, search_has_criteria=True),
    )
    if retrieve is None or retrieve.action is not MetaAction.ACT:
        return False, f"retrieve_ready SEARCH must → ACT, got {retrieve}"
    # Content known + unclosed reveal → EXPLORE, not re-ACT
    route = sanitize_meta_choice(
        {"meta_action": "act", "why": "click again", "confidence": 0.9},
        MetaContext(
            route_discovery_owed=True,
            incomplete_reveal=True,
            retrieve_ready=True,
            address_known=True,
            search_has_criteria=True,
        ),
    )
    if route is None or route.action is not MetaAction.EXPLORE:
        return False, f"incomplete_reveal ACT must → EXPLORE, got {route}"
    route_search = sanitize_meta_choice(
        {"meta_action": "search", "why": "search again", "confidence": 0.8},
        MetaContext(route_discovery_owed=True, incomplete_reveal=True),
    )
    if route_search is None or route_search.action is not MetaAction.EXPLORE:
        return False, f"route_discovery SEARCH must → EXPLORE, got {route_search}"
    # Referent mismatch → ACT repair, not EXPLORE thrash
    repair = sanitize_meta_choice(
        {"meta_action": "explore", "why": "probe again", "confidence": 0.9},
        MetaContext(referent_repair_owed=True, has_grounded_action=True),
    )
    if repair is None or repair.action is not MetaAction.ACT:
        return False, f"referent_repair EXPLORE must → ACT, got {repair}"
    # Legacy verify token must not parse; perceive is canonical.
    if _parse_action({"meta_action": "verify"}) is not None:
        return False, "legacy verify token must not parse"
    verify = sanitize_meta_choice(
        {"meta_action": "perceive", "why": "check", "confidence": 0.8},
        MetaContext(),
    )
    if verify is None or verify.action is not MetaAction.PERCEIVE:
        return False, f"perceive must stay PERCEIVE, got {verify}"
    # Meta packet exposes intent/result/unexplored
    pkt_ctx = MetaContext(
        search_episode=getattr(st, "search_episode", None),
        search_episode_failed=True,
        search_exhausted=True,
        search_has_criteria=True,
    )
    pkt = meta_context_packet(pkt_ctx)
    rs = (pkt.get("search") or {}).get("referent_search") or {}
    if not isinstance(rs.get("intent"), dict) or not rs["intent"].get("sought"):
        return False, "meta packet missing SearchIntent"
    if not isinstance(rs.get("result"), dict):
        return False, "meta packet missing SearchResult"
    if not rs.get("unexplored_scopes"):
        return False, "meta packet missing unexplored_scopes"
    return True, "SEARCH contract + EXPLORE + retrieve/route/verify hygiene"


def _reveal_geometry_mismatch_prefers_landed_not_intended() -> Tuple[bool, str]:
    """Live 125715: geometry mismatch must not rewrite object geometry from landing.

    Motor landing updates Attempt.motor_point only. Seed + brain must re-perceive
    (inconclusive_grounding), never act at intended latch or landed-as-object.
    """
    from plugin.agent.brain import apply_surprise_explanation
    from plugin.agent.decision_consultation import DecisionOutcome
    from plugin.agent.reflect_diagnosis import seed_reflect_diagnosis_from_measured
    from plugin.agent.unified_cognition import finalize_surprise_explanation
    from plugin.agent.runtime.state import ExecutionState

    packet = {
        "action": {
            "family": "reveal_actions",
            "target": "zarooratwala",
            "executor_ok": True,
            "intended_point": [1191.0, 201.0],
            "motor_landed_point": [878.0, 260.0],
        },
        "expected": {"surface": "context_menu"},
        "actual": {
            "predicted_surface": "context_menu",
            "observed_surface": "conversation",
            "matched": False,
        },
        "measured": {
            "geometry_mismatch": True,
            "executor_ok": True,
            "motor_landed_point": [878.0, 260.0],
        },
        "post_world": {
            "surface": "conversation",
            "objects": [
                {
                    "text": "https://www.zarooratwala.com/",
                    "kind": "message_bubble",
                    "point": [900, 255],
                    "matches_goal": True,
                },
                {
                    "text": "other",
                    "kind": "message_bubble",
                    "point": [1191, 201],
                    "matches_goal": False,
                },
            ],
        },
    }
    seed = seed_reflect_diagnosis_from_measured(packet)
    if seed.repair.kind != "reperceive":
        return False, f"expected reperceive (not landed rewrite), got {seed.repair.kind}"
    if seed.recommended_next != "reperceive":
        return False, f"expected recommended_next=reperceive, got {seed.recommended_next}"
    geo = seed.repair.geometry or seed.corrected_point
    if geo is not None:
        return False, f"must not promote landing/object XY as corrected_point: {geo}"
    intended_key = "reveal_actions|zarooratwala|1191,201"
    landed_key = "reveal_actions|zarooratwala|878,260"
    dnr = {str(x) for x in (seed.do_not_repeat or [])}
    if intended_key not in dnr:
        return False, f"must forbid intended latch, got {sorted(dnr)}"
    if landed_key not in dnr:
        return False, f"must forbid landed-as-retry, got {sorted(dnr)}"

    expl = finalize_surprise_explanation(
        {"cause": "unknown", "confidence": 0.2},
        reflect_packet=packet,
    )
    state = ExecutionState()
    state.perception_mode = "reflect"
    state.last_surprise_explanation = expl
    state.last_plan_step = type(
        "S",
        (),
        {
            "action_family": "reveal_actions",
            "semantic_target": "zarooratwala",
            "target_point": [1191, 201],
        },
    )()
    steered = apply_surprise_explanation(
        DecisionOutcome(
            ok=True,
            capability="reveal_actions",
            target="zarooratwala",
            why="retry",
            confidence=0.9,
            realization="llm_decision",
        ),
        state,
    )
    if steered.capability != "observe":
        return False, f"brain must observe after mismatch, got {steered.capability}"
    if getattr(state, "reflect_corrected_point", None) is not None:
        return False, f"brain must not stash landed XY: {state.reflect_corrected_point}"
    return True, "geometry_mismatch → inconclusive re-perceive (no motor→object rewrite)"


def _ax_search_binds_compose_without_vlm_object() -> Tuple[bool, str]:
    """Live 123746: compose must bind AX Search when VLM objects are only rows.

    Contracts:
    (1) frontier actuator Q Search → compose_search_query keeps geometry;
    (2) chat_row / matches_goal Pallavi must not become the type site;
    (3) without AX/OCR Search, geometry_required_missing demotes to observe
        (no invent — preserves 095344).
    """
    from plugin.agent.decision_consultation import apply_decision_consultation
    from plugin.agent.features import StateFeatures
    from plugin.agent.goal import Goal
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import UnifiedProposal

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    rows_only = {
        "surface": "chat_list",
        "objects": [
            {
                "id": "pallavi_row",
                "kind": "chat_row",
                "text": "Pallavi",
                "matches_goal": True,
                "point": [2176, 173],
            }
        ],
    }

    class _Compose:
        def choose(self, system: str, packet: dict) -> dict:
            return {
                "capability": "compose_search_query",
                "target": "",
                "why": "search",
                "confidence": 0.9,
            }

    state = ExecutionState()
    state.unified_world_document = rows_only
    state.last_affordance_frontier = {
        "surface": "chat_list",
        "observed_actions": [
            {
                "family": "compose_search_query",
                "target_label": "Q Search",
                "target_id": 14,
                "actuators": [
                    {"type": "coordinate_click", "point": [160, 106], "confidence": 0.9}
                ],
            }
        ],
    }
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        world_model=rows_only,
        next_action={},
        confidence=0.9,
    )
    apply_decision_consultation(
        proposal,
        goal,
        features=StateFeatures(extras={}),
        execution_state=state,
        chooser=_Compose(),
    )
    na = proposal.next_action or {}
    if na.get("family") != "compose_search_query":
        return False, f"expected compose, got {na.get('family')}"
    if na.get("target_point") != [160.0, 106.0]:
        return False, f"AX Search point not bound: {na.get('target_point')}"
    if na.get("target_id") == "pallavi_row":
        return False, "must not bind chat_row for compose"

    # Stashed perception geometry (thin frontier, no actuators) must still bind.
    state_stash = ExecutionState()
    state_stash.unified_world_document = rows_only
    state_stash.last_affordance_frontier = {
        "surface": "chat_list",
        "observed_actions": [
            {"family": "open_entity", "target_label": "Pallavi", "target_id": "pallavi_row"}
        ],
    }
    state_stash.last_filter_geometry = {
        "target_label": "Search",
        "target_point": [160.0, 106.0],
        "coordinate_space": "screen",
        "geometry_source": "ax_evidence",
        "kind": "search_field",
    }
    proposal_s = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        world_model=rows_only,
        next_action={},
        confidence=0.9,
    )
    apply_decision_consultation(
        proposal_s,
        goal,
        features=StateFeatures(extras={}),
        execution_state=state_stash,
        chooser=_Compose(),
    )
    na_s = proposal_s.next_action or {}
    if na_s.get("family") != "compose_search_query" or na_s.get("target_point") != [
        160.0,
        106.0,
    ]:
        return False, f"stashed filter geometry failed: {na_s}"

    state2 = ExecutionState()
    state2.unified_world_document = rows_only
    proposal2 = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        world_model=rows_only,
        next_action={},
        confidence=0.9,
    )
    trace = apply_decision_consultation(
        proposal2,
        goal,
        features=StateFeatures(extras={}),
        execution_state=state2,
        chooser=_Compose(),
    )
    if (proposal2.next_action or {}).get("family") != "observe":
        return False, "without Search geometry must demote to observe"
    if "geometry_required_missing" not in str(trace.get("realization") or ""):
        return False, f"expected geometry_required_missing, got {trace.get('realization')}"
    return True, "ax_search_bind+stash+no_chat_row+no_invent_ok"


def _post_accept_promote_and_multipass_explore() -> Tuple[bool, str]:
    """After reveal look, promote from accepted doc; ungrounded handoff relooks.

    Covers the 235701 class: overlay pixels/OCR had Forward but pre-stage1
    reconcile on the prior document left affordance_set empty. Contracts:
    (1) promote_frontier_after_accept grounds Forward from accepted menu objects;
    (2) incomplete handoff + no menu objects ⇒ needs_relook / must_executive_reperceive;
    (3) no invented Forward when the document lacks menu items (no OCR bypass);
    (4) handoff alone (empty last_action_family) still promotes;
    (5) 125715: OCR menu verbs enrich document under handoff then promote;
        'Forwarded' chrome alone must not invent Forward.
    """
    from types import SimpleNamespace

    from plugin.agent.affordance_explore import close_current_node_frontier
    from plugin.agent.affordance_frontier import Affordance, AffordanceFrontier, STATUS_LATENT
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.world_critic import promote_frontier_after_accept, reconcile_frontier

    state = ExecutionState()
    state.reveal_handoff = {
        "surface": "context_menu",
        "ttl": 2,
        "incomplete_reveal": True,
    }
    state.last_plan_step = SimpleNamespace(action_family="reveal_actions")
    doc = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [
            {"text": "Forward", "kind": "menu_item", "is_menu_item": True, "point": [10, 20]},
            {"text": "Reply", "kind": "menu_item", "is_menu_item": True, "point": [10, 40]},
        ],
    }
    status = promote_frontier_after_accept(
        state, accepted_document=doc, last_action_family="reveal_actions"
    )
    if not status.get("promoted") or not state.last_grounded_affordance_set:
        return False, f"post-accept promote failed: {status}"
    labels = {
        str(a.get("target_label") or "")
        for a in state.last_grounded_affordance_set
    }
    if "Forward" not in labels:
        return False, f"Forward not grounded after accept, got {labels}"

    state2 = ExecutionState()
    state2.reveal_handoff = {
        "surface": "context_menu",
        "ttl": 4,
        "incomplete_reveal": True,
        "explore_budget": 2,
        "explore_used": 0,
    }
    report = close_current_node_frontier(
        accepted_world={
            "surface": "conversation",
            "objects": [{"text": "yeah", "kind": "message", "point": [1, 1]}],
        },
        passive_frontier={"surface": "conversation"},
        execution_state=state2,
    )
    if not report.get("needs_relook") or not state2.must_executive_reperceive:
        return False, f"ungrounded handoff must schedule relook, got {report}"
    if any(
        str(a.get("target_label") or "").lower() == "forward"
        for a in (state2.last_grounded_affordance_set or [])
    ):
        return False, "must not invent Forward without menu objects in document"

    state3 = ExecutionState()
    state3.reveal_handoff = {"surface": "context_menu", "ttl": 2}
    frontier = AffordanceFrontier(
        surface="conversation",
        latent_actions=[
            Affordance(
                id="fwd",
                family="invoke_affordance",
                status=STATUS_LATENT,
                target_label="Forward",
            )
        ],
    )
    reconcile_frontier(
        frontier,
        document={
            "surface": "conversation",
            "objects": [{"text": "Forward", "kind": "menu_item", "point": [5, 5]}],
        },
        execution_state=state3,
        last_action_family="",
    )
    if not any(
        a.target_label == "Forward" and a.actuators for a in frontier.observed_actions
    ):
        return False, "handoff without plan-step family must still promote Forward"

    # 125715: OCR Forward with geometry under handoff → enrich → promote.
    state4 = ExecutionState()
    state4.reveal_handoff = {
        "surface": "context_menu",
        "ttl": 2,
        "incomplete_reveal": True,
    }
    ocr_status = promote_frontier_after_accept(
        state4,
        accepted_document={
            "surface": "conversation",
            "objects": [
                {
                    "text": "Forwarded: note",
                    "kind": "message_bubble",
                    "point": [1, 1],
                }
            ],
        },
        last_action_family="reveal_actions",
        ocr_lines=[{"text": "Forward", "bounds": [100.0, 200.0, 60.0, 20.0]}],
    )
    ocr_labels = {
        str(a.get("target_label") or "")
        for a in (state4.last_grounded_affordance_set or [])
    }
    if not ocr_status.get("ocr_enriched") or "Forward" not in ocr_labels:
        return False, f"OCR menu enrich must promote Forward, got {ocr_status} {ocr_labels}"

    state5 = ExecutionState()
    state5.reveal_handoff = {"surface": "context_menu", "ttl": 2, "incomplete_reveal": True}
    bad = promote_frontier_after_accept(
        state5,
        accepted_document={
            "surface": "conversation",
            "objects": [
                {"text": "Forwarded: note", "kind": "message_bubble", "point": [1, 1]}
            ],
        },
        last_action_family="reveal_actions",
        ocr_lines=[{"text": "Forwarded", "bounds": [100.0, 200.0, 60.0, 20.0]}],
    )
    bad_labels = {
        str(a.get("target_label") or "")
        for a in (state5.last_grounded_affordance_set or [])
    }
    if bad.get("ocr_enriched") or any(str(x).strip().lower() == "forward" for x in bad_labels):
        return False, f"Forwarded chrome must not invent Forward, got {bad} {bad_labels}"

    return True, "post_accept_promote+multipass_relook+ocr_enrich_ok"


def _overlay_capture_includes_menu_layer_after_reveal() -> Tuple[bool, str]:
    """After reveal, capture must composite menu layers (150708 class).

    Window-scoped ``screencapture -l`` only includes layer-0 app windows, so an
    open macOS context menu never reaches the VLM. Contracts:
    (1) reveal_handoff ⇒ expects_overlay_perception;
    (2) overlay expectancy ⇒ capture mode overlay_display (not window);
    (3) without handoff, ordinary looks stay window-scoped;
    (4) menu_item Forward in the document promotes under handoff.
    """
    from plugin.agent.affordance_frontier import Affordance, AffordanceFrontier, STATUS_LATENT
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import expects_overlay_perception
    from plugin.agent.world_critic import reconcile_frontier
    from plugin.perception.macos.accessibility.observer import (
        resolve_screenshot_capture_mode,
    )

    plain = ExecutionState()
    if expects_overlay_perception(plain):
        return False, "no-handoff must not expect overlay"
    if resolve_screenshot_capture_mode(include_overlays=False) != "window":
        return False, "default capture must be window"

    state = ExecutionState()
    state.reveal_handoff = {
        "surface": "context_menu",
        "ttl": 2,
        "incomplete_reveal": True,
    }
    if not expects_overlay_perception(state):
        return False, "reveal_handoff must expect overlay perception"
    mode = resolve_screenshot_capture_mode(
        include_overlays=expects_overlay_perception(state)
    )
    if mode != "overlay_display":
        return False, f"overlay expectancy must select overlay_display, got {mode!r}"

    frontier = AffordanceFrontier(
        surface="conversation",
        latent_actions=[
            Affordance(
                id="fwd",
                family="invoke_affordance",
                status=STATUS_LATENT,
                target_label="Forward",
            )
        ],
    )
    reconcile_frontier(
        frontier,
        document={
            "surface": "conversation",
            "objects": [
                {"text": "Forward", "kind": "menu_item", "is_menu_item": True, "point": [10, 20]},
                {"text": "Reply", "kind": "menu_item", "is_menu_item": True, "point": [10, 40]},
            ],
        },
        execution_state=state,
        last_action_family="reveal_actions",
    )
    labels = {a.target_label for a in frontier.observed_actions}
    if "Forward" not in labels or not frontier.observed_actions[-1].actuators:
        return False, f"handoff+menu_item must promote Forward, got {labels}"
    if not state.last_grounded_affordance_set:
        return False, "affordance_set not published after overlay document"
    return True, "overlay_display+menu_promote_ok"


def _reveal_grounds_affordance_set_not_phash_skip() -> Tuple[bool, str]:
    """After reveal_actions, overlay expectancy must force vision and ground Forward.

    Covers the 112904 class: motor-ok context-click + phash/AX no_effect left an
    empty affordance_set so the brain re-revealed forever. Contracts:
    (1) probe outcome is incomplete_reveal until geometry exists;
    (2) overlay handoff/intention blocks post-act phash reuse;
    (3) handoff + menu objects promote even when flat surface stays conversation;
    (4) reveal_actions post-perceive profile exists.
    """
    from plugin.agent.affordance_frontier import Affordance, AffordanceFrontier, STATUS_LATENT
    from plugin.agent.capabilities.base import AddressableEntity
    from plugin.agent.capabilities.reveal_actions import reveal_actions
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.transition.post_perceive import profile_for
    from plugin.agent.unified_cognition import expects_overlay_perception
    from plugin.agent.world_critic import reconcile_frontier

    class _Ptr:
        def activate(self, app):
            return True, "ok"

        def context_click(self, app, label, bounds=None):
            return True, "clicked"

        def hover(self, app, label, bounds=None):
            return True, "hover"

    state = ExecutionState()
    result = reveal_actions(
        AddressableEntity(app="WhatsApp", label="link", bounds=(1, 2, 3, 4)),
        _Ptr(),
        context={
            "surface": "conversation",
            "frontier": {
                "latent_actions": [
                    {
                        "target_label": "Forward",
                        "family": "invoke_affordance",
                        "confidence": 0.7,
                        "reversible": True,
                    }
                ],
                "observed_actions": [],
            },
            "execution_state": state,
        },
        goal_action="Forward",
    )
    ev = result.to_outcome().evidence
    if not ev.get("incomplete_reveal") or ev.get("substrate") != "addressable_entity":
        return False, f"probe must be incomplete_reveal/addressable_entity, got {ev}"
    if not isinstance(state.reveal_handoff, dict):
        return False, "reveal_handoff not recorded"
    if not expects_overlay_perception(state):
        return False, "handoff must block phash / expect overlay perception"
    state.unified_last_expectation = {"surface": "context_menu"}
    state.reveal_handoff = None
    if not expects_overlay_perception(state):
        return False, "act_intention context_menu must expect overlay perception"

    state2 = ExecutionState()
    state2.reveal_handoff = {"surface": "context_menu", "ttl": 2}
    frontier = AffordanceFrontier(
        surface="conversation",
        latent_actions=[
            Affordance(
                id="fwd",
                family="invoke_affordance",
                status=STATUS_LATENT,
                target_label="Forward",
            )
        ],
    )
    reconcile_frontier(
        frontier,
        document={
            "surface": "conversation",
            "objects": [{"text": "Forward", "kind": "menu_item", "point": [10, 20]}],
        },
        execution_state=state2,
        last_action_family="reveal_actions",
    )
    if not any(a.target_label == "Forward" and a.actuators for a in frontier.observed_actions):
        return False, "handoff+menu_item must promote Forward with actuators"
    if not state2.last_grounded_affordance_set:
        return False, "affordance_set substrate not published"
    prof = profile_for("reveal_actions")
    if "affordance_set_empty" not in prof.retry_on or prof.max_retries < 2:
        return False, "reveal_actions post-perceive profile missing affordance gate"
    return True, "incomplete_reveal+phash_block+handoff_promote+post_perceive_ok"


def _effect_judgment_survives_meta_consume() -> Tuple[bool, str]:
    """154356: suppressed_rearm must not falsify effect-absent for mechanism."""
    from plugin.agent.controller import (
        _consume_surprise,
        _effect_was_absent,
        _last_action_surprised,
        _prediction_was_contradicted,
    )
    from plugin.agent.capabilities.reveal_actions import escalate_failed_reveal
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import note_prediction_error, UnifiedProposal

    state = ExecutionState()
    state.last_prediction_error = {
        "matched": False,
        "predicted_surface": "context_menu",
        "observed_surface": "conversation",
        "verdict": "missing controls",
    }
    state.last_attribution = {
        "belief_authority": "motor",
        "effect_kind": "no_transition",
        "outcome": "no_effect",
    }
    _consume_surprise(state)
    if state.last_prediction_error.get("matched") is not False:
        return False, "consume_surprise must not set matched=True"
    if not _effect_was_absent(state):
        return False, "effect_absent judgment lost after consume"
    if _prediction_was_contradicted(state) or _last_action_surprised(state):
        return False, "meta surprise must stay disarmed after consume"
    state.unified_last_expectation = {
        "surface": "context_menu",
        "likely_controls": ["Forward"],
    }
    err = note_prediction_error(
        state,
        UnifiedProposal(
            world_model={"surface": "conversation", "objects": []},
            confidence=0.5,
        ),
    )
    if err.get("matched") is not False or not err.get("suppressed_rearm"):
        return False, f"rearm latch wrong: {err}"
    esc = escalate_failed_reveal(
        state, target="content_x", point=(1.0, 2.0), last_gesture="context_click"
    )
    if esc.get("next_mode") != "hover":
        return False, f"mechanism escalate blocked: {esc}"
    return True, "judgment_honest+meta_disarmed+escalate_ok"


def _content_probe_requires_referent_fit() -> Tuple[bool, str]:
    """154356: content probe must not bind a non-overlapping model target."""
    from plugin.agent.decision_consultation import _ground_choice_on_world

    doc = {
        "surface": "conversation",
        "objects": [
            {
                "id": "wrong",
                "kind": "message_bubble",
                "text": "content_beta_unrelated",
                "point": [10.0, 20.0],
            },
            {
                "id": "right",
                "kind": "message_bubble",
                "text": "https://example.test/goal_token_alpha/path",
                "point": [30.0, 40.0],
                "matches_goal": True,
            },
        ],
    }
    grounded = _ground_choice_on_world(
        doc,
        "reveal_actions",
        "content_beta_unrelated",
        goal_referents=["goal_token_alpha"],
    )
    if grounded.get("target_id") != "right":
        return False, f"expected rebind to right, got {grounded}"
    return True, "referent_rebind_ok"


def _failed_reveal_escalates_off_context_click() -> Tuple[bool, str]:
    """LIVE 153213: incomplete reveal must rotate gesture, not re-context-click.

    Motor-ok context_click without a menu left OPEN_FORWARD looping the same
    bubble. Contract: failed_reveal latches the gesture fingerprint, advances
    reveal_probe_mode to hover, then select_content; actor honors hover override.
    """
    from plugin.agent.actor import brief_from_brain_choice
    from plugin.agent.affordance_frontier import AffordanceFrontier, finalize_reveal_handoff
    from plugin.agent.capabilities.reveal_actions import (
        escalate_failed_reveal,
        reveal_motor_fingerprint,
    )
    from plugin.agent.runtime.state import ExecutionState

    state = ExecutionState()
    state.reveal_handoff = {
        "surface": "context_menu",
        "ttl": 2,
        "looks": 0,
        "probe_gesture": "context_click",
        "incomplete_reveal": True,
    }
    state.last_plan_step = type(
        "S",
        (),
        {
            "action_family": "reveal_actions",
            "semantic_target": "ZarooratWala",
            "target_point": (380.0, 210.0),
        },
    )()
    frontier = AffordanceFrontier(surface="conversation")
    finalize_reveal_handoff(state, frontier)
    status = finalize_reveal_handoff(state, frontier)
    # Method settle miss advances under surviving intention (not episode death).
    if not (status.get("method_advance") or status.get("failed_reveal")):
        return False, f"expected method_advance or failed_reveal, got {status}"
    if state.reveal_probe_mode != "hover":
        return False, f"expected hover after failed context_click, got {state.reveal_probe_mode!r}"
    key = reveal_motor_fingerprint("context_click", "ZarooratWala", (380.0, 210.0))
    if key not in (state.avoid_motor_keys or []):
        return False, f"missing avoid key {key}"
    esc = escalate_failed_reveal(
        state,
        target="ZarooratWala",
        point=(380.0, 210.0),
        last_gesture="hover",
    )
    if esc.get("next_mode") != "select_content":
        return False, f"expected select_content after hover fail, got {esc}"
    if state.reveal_prefer_capability != "select_content":
        return False, "reveal_prefer_capability must be select_content"
    brief = brief_from_brain_choice(
        {
            "family": "reveal_actions",
            "target_label": "ZarooratWala",
            "target_point": [380.0, 210.0],
            "gesture": "hover",
            "coordinate_space": "screen",
        },
        {
            "surface": "conversation",
            "objects": [
                {
                    "text": "ZarooratWala",
                    "kind": "message_bubble",
                    "point": [380.0, 210.0],
                }
            ],
        },
        app="WhatsApp",
        capability="reveal_actions",
    )
    if brief.gesture != "hover":
        return False, f"actor ignored hover override: {brief.gesture!r}"
    return True, "failed_reveal→hover→select_content+actor_hover_ok"


def _storage_pressure_routes_to_housekeeping_capability() -> Tuple[bool, str]:
    """Under storage_pressure, meta ACT must name housekeeping — not goal search.

    Covers the 103111 class: WhatsApp 'Storage is too full' blocks the task UI;
    the meta packet must offer housekeeping verbs and sanitize must keep/prefer
    relieve_host_storage. Staged cleanup must expose headroom-stop API shape.
    """
    from plugin.agent.capabilities.catalog import realized_verbs
    from plugin.agent.capabilities.dispatch import can_dispatch
    from plugin.agent.executive.meta_action import MetaAction, MetaContext
    from plugin.agent.executive.meta_consultation import (
        meta_context_packet,
        sanitize_meta_choice,
    )
    from plugin.agent.executive.meta_situation import MetaSituation
    from plugin.agent.runtime.recovery import _load_disk_cleanup_library
    from plugin.evals.golden.schema import load_module_cases
    from plugin.evals.golden.score import score_meta_action_case

    for verb in ("relieve_host_storage", "recover_blocked_app"):
        if verb not in realized_verbs() or not can_dispatch(verb):
            return False, f"{verb} not realized/dispatchable"

    sit = MetaSituation(
        blockers={
            "storage_pressure": True,
            "system_warnings": ["Storage is too full"],
            "exit_cta_visible": True,
        },
        housekeeping_capabilities=[
            {"name": "relieve_host_storage", "why": "free space"},
            {"name": "recover_blocked_app", "why": "relaunch"},
        ],
    )
    packet = meta_context_packet(MetaContext(), situation=sit)
    if not packet.get("blockers", {}).get("storage_pressure"):
        return False, "meta packet missing storage_pressure blockers"
    hk = (packet.get("options") or {}).get("housekeeping_capabilities") or []
    if not any(c.get("name") == "relieve_host_storage" for c in hk if isinstance(c, dict)):
        return False, "meta packet missing relieve_host_storage offer"

    choice = sanitize_meta_choice(
        {
            "meta_action": "act",
            "capability": "compose_search_query",
            "why": "search pallavi",
            "confidence": 0.9,
        },
        MetaContext(),
        situation=sit,
    )
    if choice is None or choice.action is not MetaAction.ACT:
        return False, f"sanitize dropped ACT under storage pressure: {choice}"
    if choice.capability != "relieve_host_storage":
        return False, f"sanitize kept wrong capability: {choice.capability!r}"

    lib = _load_disk_cleanup_library()
    if not hasattr(lib, "relieve_until_headroom"):
        return False, "disk_cleanup missing relieve_until_headroom"
    already = lib.relieve_until_headroom(target_free_bytes=1)
    if "stages" not in already or "target_free_bytes" not in already:
        return False, f"relieve_until_headroom shape bad: {already}"

    cases = [
        c
        for c in load_module_cases("meta_action")
        if "housekeeping" in (c.tags or []) or "failure_103111" in (c.tags or [])
    ]
    if len(cases) < 2:
        return False, f"too few housekeeping meta goldens: {len(cases)}"
    for case in cases:
        scored = score_meta_action_case(case)
        if not scored.passed:
            return False, f"golden failed: {case.id} {scored.checks}"
    return True, f"housekeeping_meta_cases={len(cases)}; relieve_preferred"


def _phenomenon_curriculum_hard_contracts() -> Tuple[bool, str]:
    """Phenomenon goldens from live failures must stay green (zero-regression).

    Covers warning≠blocker, executability interrupt, child dedupe, effect≠exec_ok,
    no premature resume, no unsafe user cleanup — seeded from 20260810_161105.
    """
    from plugin.evals.phenomena.score import blocking_failures, score_all

    report = score_all()
    fails = blocking_failures(report)
    if fails:
        return False, f"{len(fails)} phenomenon fails: {fails[:3]}"
    total = int(report.get("total") or 0)
    if total < 10:
        return False, f"phenomenon corpus too small: {total}"
    return True, f"phenomena_pass={report.get('passed')}/{total}"


def _foreign_attempt_progress_does_not_verify_forward() -> Tuple[bool, str]:
    """Capability implications must be attempt-scoped (no foreign progress)."""
    from types import SimpleNamespace

    from plugin.agent.executive.effect_implications import collect_effect_evidence
    from plugin.agent.runtime.state import ExecutionState

    state = ExecutionState()
    state.last_plan_step = SimpleNamespace(
        action_family="invoke_affordance",
        semantic_target="Forward",
        attempt_id="attempt-B",
    )
    state.last_result = {"ok": True, "attempt_id": "attempt-B"}
    state.last_attribution = {
        "effect_kind": "progress",
        "attempt_id": "attempt-A",
    }
    state.last_effect_attempt_id = "attempt-A"
    evidence = collect_effect_evidence(state, {"surface": "conversation"})
    if "source_object_selected" in evidence.implies:
        return False, "foreign attempt progress retired source_object_selected"
    if "forward_route_discovered" in evidence.achieved:
        return False, "foreign attempt progress claimed forward_route_discovered"
    # Same-attempt generic progress still insufficient without named predicate/surface.
    state.last_attribution = {
        "effect_kind": "progress",
        "attempt_id": "attempt-B",
    }
    state.last_effect_attempt_id = "attempt-B"
    evidence2 = collect_effect_evidence(state, {"surface": "conversation"})
    if "forward_route_discovered" in evidence2.achieved:
        return False, "generic progress implied forward_route_discovered"
    # Unscoped named predicates (no effect-side attempt id) fail closed.
    state.last_result = {"ok": True}
    state.last_attribution = {
        "verified_effect_predicates": ["forward_surface_open"],
    }
    state.last_effect_attempt_id = ""
    evidence3 = collect_effect_evidence(state, {"surface": "conversation"})
    if "source_object_selected" in evidence3.implies:
        return False, "unscoped named effect verified current attempt"
    return True, "attempt-scoped effect evidence ok"


def _foreign_result_plus_picker_does_not_bind_via_action() -> Tuple[bool, str]:
    """Stale last_result + ambient picker must not mutate task via bind path."""
    from plugin.agent.action import Action
    from plugin.agent.controller import _bind_forward_after_execution
    from plugin.agent.runtime.state import RuntimeState
    from plugin.worldmodel.model import WorldModel

    rt = RuntimeState(world_model=WorldModel(active_app="WhatsApp"))
    rt.execution_state.last_surface = "forward_picker"
    rt.execution_state.last_result = {"ok": True}
    rt.world_model.overlay_hints = {
        "forward_task": {
            "predicates": {"source_object_selected": False},
            "derived_phase": "FIND_LINK",
        }
    }
    _bind_forward_after_execution(
        rt,
        Action(
            action="InvokeAffordance",
            action_family="invoke_affordance",
            semantic_target="Forward",
            attempt_id="attempt-forward-now",
        ),
    )
    preds = ((rt.world_model.overlay_hints or {}).get("forward_task") or {}).get(
        "predicates"
    ) or {}
    if preds.get("source_object_selected") is True:
        return False, "stale result + picker latched source_object_selected via bind"
    return True, "bind path does not pair stale result with picker"


def _open_conversation_sync_closes_open_source() -> Tuple[bool, str]:
    """Pipeline: open_conversation matches goal contact → FIND_LINK."""
    from plugin.agent.apps.whatsapp import build_forward_task_state
    from plugin.agent.goal import Goal
    from plugin.agent.whatsapp_view import WhatsAppWorldView
    from plugin.worldmodel.entities.entity import Entity
    from plugin.worldmodel.model import WorldModel

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Alice",
        target_contact="Bob",
        link_query="example",
    )
    wm = WorldModel(active_app="WhatsApp")
    wm.entities[1] = Entity(
        id=1,
        entity_type="static",
        semantic_role="Alice",
        label="Alice",
        role="AXStaticText",
        bounds=(100.0, 40.0, 40.0, 16.0),
        actions=[],
        attributes={},
        visible=True,
    )
    view = WhatsAppWorldView(screen="CONVERSATION", open_conversation="Alice")
    prior = {
        "predicates": {"source_conversation_open": False},
        "derived_phase": "OPEN_SOURCE",
    }
    state = build_forward_task_state(goal, wm, view, leftover=False, prior=prior)
    if not state.predicates.source_conversation_open:
        return False, "source_conversation_open not synchronized from open_conversation"
    if state.derived_phase != "FIND_LINK":
        return False, f"expected FIND_LINK, got {state.derived_phase}"
    if state.binding("source_conversation").status != "confirmed":
        return False, "source_conversation binding not confirmed"
    return True, "open_conversation sync closes OPEN_SOURCE"


def _scoped_method_avoid_respects_world_signature() -> Tuple[bool, str]:
    """Point-free method avoid must not stick across world signature changes."""
    from plugin.agent.controller import _note_failed_motor
    from plugin.agent.executive.effect_implications import (
        avoid_key_blocks_method,
        method_context_from_state,
    )
    from plugin.agent.executive.intention_frame import (
        MethodContext,
        active_intention_frame,
        push_intention_frame,
        seed_reveal_explore_frame,
    )
    from plugin.agent.runtime.state import RuntimeState
    from plugin.worldmodel.model import WorldModel

    rt = RuntimeState(world_model=WorldModel(active_app="App"))
    rt.execution_state.last_surface = "search"
    push_intention_frame(rt.execution_state, seed_reveal_explore_frame())
    hit = "https://www.example.com/item"
    _note_failed_motor(rt, family="open_entity", target=hit, point=(10.0, 20.0))
    keys = list(rt.execution_state.avoid_motor_keys or [])
    iframe = active_intention_frame(rt.execution_state)
    search_sig = method_context_from_state(
        rt.execution_state, world={"surface": "search"}
    ).signature()
    if not avoid_key_blocks_method(
        keys,
        family="open_entity",
        target=hit,
        intention_id=iframe.intention.id,
        world_signature=search_sig,
    ):
        return False, "same-signature method avoid missing"
    conv_sig = MethodContext(surface="conversation").signature()
    if avoid_key_blocks_method(
        keys,
        family="open_entity",
        target=hit,
        intention_id=iframe.intention.id,
        world_signature=conv_sig,
    ):
        return False, "method avoid stuck across world signature change"
    return True, "scoped method avoid ok"


def _foreign_open_conversation_triggers_leave_before_compose() -> Tuple[bool, str]:
    """Live 145943: foreign open must not compose; meta ACT leave instead."""
    from plugin.agent.decision_consultation import build_decision_brief, sanitize_decision
    from plugin.agent.executive.meta_action import MetaAction, MetaContext
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice
    from plugin.agent.features import StateFeatures
    from plugin.agent.goal import Goal

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    brief = build_decision_brief(
        goal,
        world_document={
            "surface": "conversation",
            "open_conversation": "[CoE - IoT & AI] BLR Startups",
            "objects": [
                {"kind": "search_field", "text": "Search", "point": [120.0, 80.0]},
            ],
        },
        features=StateFeatures(conversation_open=True, extras={}),
    )
    rejected = sanitize_decision(
        {"capability": "compose_search_query", "target": ""}, brief
    )
    why_l = (rejected.why or "").lower()
    if rejected.ok or (
        "foreign" not in why_l and "wrong_locus:container" not in why_l
    ):
        return False, f"compose not blocked on foreign open: {rejected.why}"
    choice = sanitize_meta_choice(
        {"meta_action": "search", "why": "find", "confidence": 0.9},
        MetaContext(leave_wrong_conversation_owed=True),
    )
    if choice is None or choice.action is not MetaAction.ACT:
        return False, f"meta did not ACT for leave debt: {choice}"
    return True, "foreign open leave-before-compose ok"


def _wrong_field_locus_forbids_type_when_composer_focused() -> Tuple[bool, str]:
    """Composer-focused locate/type must be forbidden (wrong field locus)."""
    from plugin.agent.decision_consultation import build_decision_brief, sanitize_decision
    from plugin.agent.features import StateFeatures
    from plugin.agent.goal import Goal

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    brief = build_decision_brief(
        goal,
        world_document={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "focused_field_role": "composer",
            "objects": [],
        },
        features=StateFeatures(conversation_open=True, extras={}),
    )
    rejected = sanitize_decision(
        {"capability": "locate_content", "target": "zarooratwala"}, brief
    )
    why = (rejected.why or "").lower()
    if rejected.ok or ("composer" not in why and "wrong_locus" not in why):
        return False, f"locate not blocked on composer: {rejected.why}"
    return True, "wrong field locus forbids type/locate on composer"


def _locate_effect_unknown_contracts() -> Tuple[bool, str]:
    """185549: blind locate → UNKNOWN; trustworthy negative → NOT_ACHIEVED.

    Also: still_unobservable ≠ INEFFECTIVE; MethodFrontier advances; matches_goal
    alone cannot authorize source_object binding.
    """
    from plugin.agent.capabilities.locate_content import (
        note_locate_outcome,
        prefer_next_locate_realization,
        resolve_locate_effect_verification,
        same_locate_unresolved,
    )
    from plugin.agent.decision_consultation import (
        DecisionBrief,
        TaskState,
        _content_search_locate_outcome,
    )
    from plugin.agent.executive.intention_frame import (
        MethodOutcome,
        MethodStatus,
        active_intention_frame,
    )
    from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.source_query_binding import evaluate_source_object_match

    # Trustworthy negative must not arm UNKNOWN / verify debt.
    neg = ExecutionState()
    neg_info = note_locate_outcome(
        neg,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="scroll_scan",
        message="scanned 12 screenful(s) without a match; budget reached",
        exhausted=True,
    )
    if neg_info.get("effect_status") != "not_achieved" or neg.locate_effect_verify_owed:
        return False, f"exhausted/negative must be NOT_ACHIEVED, got {neg_info}"

    state = ExecutionState()
    info = note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="native_find",
        message="queried via find; accessibility text unavailable, screen must be read",
    )
    if info.get("effect_status") != "unknown" or not state.locate_effect_verify_owed:
        return False, f"blind locate must be effect unknown+verify owed, got {info}"
    iframe = active_intention_frame(state)
    if iframe is None or not iframe.pending_effect_verification:
        return False, "pending_effect_verification not armed"
    if not any(
        a.method_outcome == MethodOutcome.EFFECT_UNCERTAIN.value for a in iframe.attempts
    ):
        return False, "attempt ledger missing EFFECT_UNCERTAIN"
    if not same_locate_unresolved(state, query="zarooratwala"):
        return False, "same locate must be unresolved while verify owed"

    brief = DecisionBrief(
        goal={"source_query": "zarooratwala", "link_query": "zarooratwala"},
        world={"surface": "conversation", "open_conversation": "Pallavi"},
        capabilities=["locate_content", "observe"],
        meta_action="search",
        task_state=TaskState(source_chat_open=True, content_located=False),
    )
    if _content_search_locate_outcome(brief, execution_state=state) is not None:
        return False, "SEARCH must not reseal identical locate while effect unknown"

    meta = select_meta_action(
        MetaContext(locate_effect_verify_owed=True, awaiting_verification=True)
    )
    if meta.action is not MetaAction.PERCEIVE:
        return False, f"meta must PERCEIVE for locate verify, got {meta}"
    san = sanitize_meta_choice(
        {"meta_action": "search", "why": "unpaid", "confidence": 0.9},
        MetaContext(locate_effect_verify_owed=True),
    )
    if san is None or san.action is not MetaAction.PERCEIVE:
        return False, f"sanitize SEARCH→PERCEIVE failed: {san}"

    draft = evaluate_source_object_match(
        text="zarooratwala lasawe",
        kind="draft",
        query="zarooratwala",
        container_open="Pallavi",
        expected_container="Pallavi",
        role="composer",
        perception_matches_goal=True,
    )
    if draft.binding_eligible:
        return False, "matches_goal/draft must not bind content patient"

    distractor = evaluate_source_object_match(
        text="https://www.instagram.com/reel/abc/",
        kind="message_bubble",
        query="zarooratwala",
        container_open="Pallavi",
        expected_container="Pallavi",
        perception_matches_goal=True,
    )
    if distractor.binding_eligible or distractor.query_match:
        return False, "distractor URL must not be query_match/binding_eligible"

    resolve_locate_effect_verification(
        state, content_located=False, query_visible=False, still_unobservable=True
    )
    iframe2 = active_intention_frame(state)
    if iframe2 is None:
        return False, "intention frame missing after still_unobservable"
    if iframe2.method_frontier.status_of("locate_native_find") != MethodStatus.UNTRIED.value:
        return False, "still_unobservable must not mark method INEFFECTIVE"
    if prefer_next_locate_realization(state) != "scroll_scan":
        return False, "MethodFrontier must surface next eligible locate method"
    seal = _content_search_locate_outcome(brief, execution_state=state)
    if seal is None or "scroll_scan" not in (seal.why + seal.realization):
        return False, f"after failed verify must reseal next frontier method, got {seal}"
    return True, "locate effect-unknown contracts ok"


def _native_find_does_not_type_when_only_composer_focused() -> Tuple[bool, str]:
    """Cmd+F no-op + composer focus ⇒ NativeFind must not type."""
    from plugin.agent.capabilities.locate_content import (
        MACOS_FIND,
        LocateRequest,
        NativeFind,
    )

    class _ComposerSurface:
        def __init__(self) -> None:
            self.typed: list = []
            self.keys: list = []

        def activate(self, app: str) -> None:
            return None

        def key(self, chord) -> None:
            self.keys.append(chord)

        def type_text(self, text: str) -> None:
            self.typed.append(text)

        def scroll(self, direction: str, amount: int) -> None:
            return None

        def surface_text(self) -> str:
            return "composer draft"

        def surface_signature(self) -> str:
            return "composer"

        def text_input_focused(self) -> bool:
            return True

        def filter_field_ready(self) -> bool:
            return False

    surface = _ComposerSurface()
    outcome = NativeFind(MACOS_FIND).locate(
        LocateRequest(query="zarooratwala", app="SomeChatApp"), surface
    )
    if outcome.ok or surface.typed:
        return False, f"typed into composer-only focus: ok={outcome.ok} typed={surface.typed}"
    return True, "native find fail-closed on composer focus"


def _wrong_container_locus_forbids_compose_into_foreign_open() -> Tuple[bool, str]:
    """Foreign open container ⇒ compose forbidden (general wrong-locus)."""
    from plugin.agent.capabilities.locus_contract import wrong_locus_forbidden
    from plugin.agent.decision_consultation import build_decision_brief
    from plugin.agent.features import StateFeatures
    from plugin.agent.goal import Goal

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    brief = build_decision_brief(
        goal,
        world_document={
            "surface": "conversation",
            "open_conversation": "[CoE - IoT & AI] BLR Startups",
            "objects": [],
        },
        features=StateFeatures(conversation_open=True, extras={}),
    )
    bad, why, req = wrong_locus_forbidden("compose_search_query", brief=brief)
    if not bad or "container" not in why:
        return False, f"container locus not forbidden: {why}"
    if req is None or req.kind.value != "container":
        return False, f"requirement kind not container: {req}"
    return True, "wrong container locus forbids compose"


def _empty_kind_high_cost_filter_fails_closed() -> Tuple[bool, str]:
    """HIGH-cost filter families refuse empty field_role/kind at motor."""
    from plugin.agent.actor import ActorBrief, validate_brief
    from plugin.agent.capabilities.action_area import validate_actuation_grounding

    ok, why = validate_actuation_grounding(
        capability="type_query",
        field_role="",
        label="",
        target_kind="",
    )
    if ok or "empty_kind" not in why:
        return False, f"empty kind not refused: ok={ok} why={why}"
    vok, vwhy = validate_brief(
        ActorBrief(
            gesture="type",
            capability="locate_content",
            field_role="none",
            label="",
            text="zarooratwala",
            point=(400.0, 400.0),
            target_kind="",
        )
    )
    if vok or ("empty_kind" not in vwhy and "wrong_locus" not in vwhy):
        return False, f"actor brief not fail-closed: ok={vok} why={vwhy}"
    return True, "empty kind high-cost filter fail-closed"


def _visible_source_chat_row_allows_open_despite_link_query() -> Tuple[bool, str]:
    """Live 145943: actuatable Pallavi chat_row may open despite unpaid link_query."""
    from plugin.agent.decision_consultation import build_decision_brief, sanitize_decision
    from plugin.agent.features import StateFeatures
    from plugin.agent.goal import Goal
    from plugin.agent.runtime.state import ExecutionState

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    brief = build_decision_brief(
        goal,
        world_document={
            "surface": "chat_list",
            "open_conversation": "[CoE - IoT & AI] BLR Startups",
            "objects": [
                {
                    "id": "pallavi_row",
                    "kind": "chat_row",
                    "text": "Pallavi",
                    "point": [180.0, 240.0],
                }
            ],
        },
        features=StateFeatures(conversation_open=True, extras={}),
        execution_state=ExecutionState(),
    )
    allowed = sanitize_decision(
        {"capability": "open_entity", "target": "Pallavi"}, brief
    )
    if not allowed.ok:
        return False, f"open_entity blocked: {allowed.why}"
    compose = sanitize_decision(
        {"capability": "compose_search_query", "target": ""}, brief
    )
    if compose.ok:
        return False, "compose still allowed with foreign open + source row"
    return True, "visible source chat_row open ok"


def _preclear_does_not_skip_when_list_with_foreign_pane() -> Tuple[bool, str]:
    """Harness preclear must not break solely on LIST/SEARCH with foreign pane."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "experiments" / "run_forward_message.py"
    text = src.read_text(encoding="utf-8")
    if "foreign_pane" not in text or "list_clean" not in text:
        return False, "preclear foreign_pane / list_clean missing"
    if "open_matches_referent" not in text:
        return False, "preclear should use open_matches_referent for on_source"
    return True, "preclear foreign pane guard present"


def _search_type_regression_with_foreign_open_keeps_reach_source_leave_debt() -> Tuple[bool, str]:
    """Foreign open leave debt must beat SEARCH after type regression."""
    from plugin.agent.executive.meta_action import MetaAction, MetaContext
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice

    choice = sanitize_meta_choice(
        {"meta_action": "search", "why": "type again", "confidence": 0.8},
        MetaContext(
            leave_wrong_conversation_owed=True,
            source_contact_open_ready=False,
            referent_search_needed=True,
            search_episode_incomplete=True,
        ),
    )
    if choice is None or choice.action is not MetaAction.ACT:
        return False, f"expected ACT leave, got {choice}"
    return True, "leave debt survives search-type regression"


def _identity_contract_does_not_block_matching_source_chat_row_open() -> Tuple[bool, str]:
    """Matching source chat_row open must not die on identity_contract."""
    from plugin.agent.decision_consultation import build_decision_brief, sanitize_decision
    from plugin.agent.features import StateFeatures
    from plugin.agent.goal import Goal
    from plugin.agent.runtime.state import ExecutionState

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    brief = build_decision_brief(
        goal,
        world_document={
            "surface": "chat_list",
            "open_conversation": "[CoE - IoT & AI] BLR Startups",
            "objects": [
                {
                    "id": "pallavi_row",
                    "kind": "chat_row",
                    "text": "Pallavi",
                    "point": [180.0, 240.0],
                }
            ],
        },
        features=StateFeatures(conversation_open=True, extras={}),
        execution_state=ExecutionState(),
    )
    decided = sanitize_decision(
        {
            "capability": "open_entity",
            "target": "Pallavi",
            "target_id": "pallavi_row",
        },
        brief,
    )
    if not decided.ok:
        return False, f"open blocked: {decided.why}"
    if "identity_contract" in (decided.why or "").lower():
        return False, decided.why
    return True, "identity contract allows source chat_row open"


def _same_surface_different_container_reconsiders_method() -> Tuple[bool, str]:
    """Same surface + different semantic_container must not keep method suppressed."""
    from plugin.agent.executive.effect_implications import (
        avoid_key_blocks_method,
        method_context_from_state,
        scoped_method_avoid_key,
    )
    from plugin.agent.executive.intention_frame import (
        active_intention_frame,
        push_intention_frame,
        seed_reveal_explore_frame,
    )
    from plugin.agent.runtime.state import RuntimeState
    from plugin.worldmodel.model import WorldModel

    rt = RuntimeState(world_model=WorldModel(active_app="App"))
    rt.execution_state.last_surface = "conversation"
    push_intention_frame(rt.execution_state, seed_reveal_explore_frame())
    hit = "https://www.example.com/item"
    iframe = active_intention_frame(rt.execution_state)
    alice = method_context_from_state(
        rt.execution_state,
        world={"surface": "conversation", "open_conversation": "Alice"},
    )
    bob = method_context_from_state(
        rt.execution_state,
        world={"surface": "conversation", "open_conversation": "Bob"},
    )
    if alice.signature() == bob.signature():
        return False, "container locus missing from MethodContext signature"
    key = scoped_method_avoid_key(
        "open_entity",
        hit,
        intention_id=iframe.intention.id,
        world_signature=alice.signature(),
    )
    if not avoid_key_blocks_method(
        [key],
        family="open_entity",
        target=hit,
        intention_id=iframe.intention.id,
        world_signature=alice.signature(),
    ):
        return False, "Alice-container method avoid missing"
    if avoid_key_blocks_method(
        [key],
        family="open_entity",
        target=hit,
        intention_id=iframe.intention.id,
        world_signature=bob.signature(),
    ):
        return False, "method avoid stuck across semantic_container change"
    return True, "same-surface different-container reconsider ok"


def _known_affordance_grounding_recovery_not_patient_substitute() -> Tuple[bool, str]:
    """Known-ungrounded Forward must trigger recovery, not bubble invoke."""
    from plugin.agent.executive.affordance_commitment import (
        arm_grounding_recovery,
        ensure_commitment_from_menu_observation,
        forbids_patient_substitute,
    )
    from plugin.agent.goal import Goal
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import UnifiedProposal, proposal_to_action
    from plugin.worldmodel.model import WorldModel

    state = ExecutionState()
    state.last_surface = "context_menu"
    state.unified_world_document = {
        "surface": "context_menu",
        "objects": [{"text": "Forward", "kind": "menu_item", "enabled": True}],
    }
    c = ensure_commitment_from_menu_observation(
        state,
        label="Forward",
        patient_ref="zarooratwala.com",
        desired_effect="forward_picker",
    )
    if c is None:
        return False, "commitment not created"
    arm_grounding_recovery(state, c, reason="label_only")
    if not forbids_patient_substitute(state, family="invoke_affordance"):
        return False, "patient substitute not forbidden"
    action, reason = proposal_to_action(
        UnifiedProposal(
            observed_state={"surface": "conversation"},
            world_model={"surface": "conversation"},
            next_action={
                "family": "invoke_affordance",
                "target_label": "Forward",
                "text": "Forward",
            },
        ),
        Goal(kind="whatsapp_forward_message"),
        WorldModel(active_app="WhatsApp"),
        execution_state=state,
    )
    if action is not None:
        return False, f"invoke rebound to patient: {reason}"
    return True, "grounding recovery blocks patient substitute"


def _effect_absent_without_grounding_evidence_does_not_force_grounding() -> Tuple[bool, str]:
    from plugin.agent.executive.affordance_commitment import (
        handle_failed_committed_action,
        upsert_commitment,
    )
    from plugin.agent.runtime.state import ExecutionState

    state = ExecutionState()
    state.unified_world_document = {
        "surface": "context_menu",
        "objects": [
            {"text": "Forward", "point": [1259.0, 290.0], "kind": "menu_item"}
        ],
    }
    upsert_commitment(
        state,
        family="invoke_affordance",
        label="Forward",
        patient_ref="msg-A",
        desired_effect="forward_picker",
    )
    result = handle_failed_committed_action(
        state,
        family="invoke_affordance",
        target="Forward",
        point=(1259.0, 290.0),
        pred_error={
            "matched": False,
            "predicted": "forward_picker",
            "actual": "conversation",
            "target": "Forward",
        },
        intended_point=(1259.0, 290.0),
        surface_before="context_menu",
    )
    if result.get("classified") == "grounding":
        return False, "effect_absent alone forced GROUNDING"
    return True, "effect_absent without evidence is not grounding"


def _same_label_different_patient_does_not_satisfy_commitment() -> Tuple[bool, str]:
    from plugin.agent.executive.affordance_commitment import (
        arm_grounding_recovery,
        commitment_satisfied_by_label_patient,
        derive_executable,
        upsert_commitment,
    )
    from plugin.agent.runtime.state import ExecutionState

    state = ExecutionState()
    c = upsert_commitment(
        state,
        family="invoke_affordance",
        label="Forward",
        patient_ref="message-A",
        owner_surface_expected="context_menu",
    )
    arm_grounding_recovery(state, c, reason="gate")
    if commitment_satisfied_by_label_patient(
        c, label="Forward", patient_ref="message-B"
    ):
        return False, "different patient incorrectly satisfied commitment"
    state.last_grounded_affordance_set = [
        {
            "target_label": "Forward",
            "patient_ref": "message-B",
            "actuators": [{"type": "coordinate_click", "point": [10.0, 20.0]}],
        }
    ]
    if derive_executable(state, c):
        return False, "patient-B Forward satisfied patient-A commitment"
    return True, "patient identity scoped"


def _prerequisite_intention_interrupts_on_blocking_condition() -> Tuple[bool, str]:
    """BlockingCondition spawns a prereq child; warnings and unmet effects do not resume.

    Covers the ZarooratWala storage-dialog class as a generic interruption:
    detect → BLOCKED_RESOLVABLE → one child per semantic effect → IntentionFrame
    judges success → parent resumes only after executability recheck.
    """
    from plugin.agent.executive.blocking import (
        ExecutabilityStatus,
        assess_executability,
        detect_warnings_and_blockers,
        resolve_methods_for_effect,
    )
    from plugin.agent.executive.intention_frame import (
        Intention,
        IntentionFrame,
        IntentionOrigin,
        ensure_child_for_precondition,
        evaluate_intention_success,
        push_intention_frame,
        resume_parent_after_child,
    )
    from plugin.agent.runtime.state import ExecutionState

    warns, blockers = detect_warnings_and_blockers(
        observation_texts=[
            "Storage is too full",
            "To keep using WhatsApp, free up at least 175.81 MB of storage.",
        ],
        view={"screen": "dialog"},
        features={"extras": {"storage_pressure": True, "has_dialog": True}},
        intention_id="i_forward",
    )
    if warns:
        return False, f"dialog misclassified as warning: {warns}"
    if not any(b.kind == "insufficient_storage" for b in blockers):
        return False, "missing insufficient_storage blocker"

    weak_w, weak_b = detect_warnings_and_blockers(
        observation_texts=["Storage almost full"],
        view={"screen": "conversation"},
        intention_id="i_forward",
    )
    if not weak_w or weak_b:
        return False, "weak storage toast must warn without interrupting"

    assessment = assess_executability(
        intention_id="i_forward",
        blockers=blockers,
        world={"surface": "dialog", "storage_pressure": True},
        facts={"agent_owned_reclaimable_bytes": 1, "storage_pressure": True},
    )
    if assessment.status != ExecutabilityStatus.BLOCKED_RESOLVABLE.value:
        return False, f"expected blocked_resolvable, got {assessment.status}"
    storage_bc = next(
        (b for b in assessment.resolvable_conditions if b.required_effect.subject == "storage"),
        None,
    )
    if storage_bc is None:
        return False, "no storage resolvable condition"
    methods = resolve_methods_for_effect(
        storage_bc.required_effect, facts={"agent_owned_reclaimable_bytes": 1}
    )
    if not methods or methods[0].capability != "relieve_host_storage":
        return False, f"wrong first method: {methods}"

    state = ExecutionState()
    parent = IntentionFrame(
        intention=Intention(
            id="i_forward",
            objective="forward",
            success_predicate="forward_affordance_grounded",
            created_from=IntentionOrigin(kind="goal"),
        )
    )
    push_intention_frame(state, parent)
    key = storage_bc.semantic_key()
    child = ensure_child_for_precondition(
        state,
        parent,
        effect_key=key,
        success_predicate=key,
        methods=[(m.capability, m.capability) for m in methods],
    )
    dup = ensure_child_for_precondition(
        state,
        parent,
        effect_key=key,
        success_predicate=key,
        methods=[(m.capability, m.capability) for m in methods],
    )
    if child is None or dup is None or child.intention.id != dup.intention.id:
        return False, "semantic dedupe failed for same required_effect"
    if not parent.suspended_by_child:
        return False, "parent not suspended_by_child"

    # Execution evidence without effect → do not resume.
    unmet_world = {"available_storage_bytes": 1_000_000, "execution_ok": True}
    if evaluate_intention_success(child, world=unmet_world):
        return False, "child success_predicate true despite unmet free bytes"
    stalled = resume_parent_after_child(state, world=unmet_world)
    if stalled.get("resumed") or stalled.get("child_effect_met"):
        return False, f"resumed/marked met while effect unmet: {stalled}"

    # Effect met but parent still non-executable → no resume.
    need = int(storage_bc.required_effect.value or 0)
    met_world = {
        "available_storage_bytes": need + 10,
        "surface": "dialog",
        "storage_pressure": True,
    }
    from plugin.agent.executive.blocking import BlockingCondition, EffectPredicate, IntentionRef

    still = [
        BlockingCondition(
            kind="app_not_operational",
            required_effect=EffectPredicate(
                subject="app_operational", relation="is_true", value=True
            ),
            blocks=[IntentionRef(intention_id="i_forward")],
        )
    ]
    after = resume_parent_after_child(
        state,
        world=met_world,
        parent_blockers=still,
        facts={
            "available_storage_bytes": need + 10,
            "app_operational": False,
            "blocked_app_recoverable": True,
        },
    )
    if not after.get("child_effect_met") or after.get("resumed"):
        return False, f"parent resumed without executability clear: {after}"
    if not after.get("parent_still_blocked"):
        return False, "expected parent_still_blocked after child met"
    return True, "prereq interrupt+dedupe+recheck ok"


def _high_cost_wrong_action_area_impossible() -> Tuple[bool, str]:
    """Wrong-area grounding for high-cost writes must be refused before motor.

    Covers the 095344 class: typing a search/filter query into a chat composer
    or contact latch. Relies on tagged goldens *and* an inline e2e so deleting
    the JSONL cases or weakening only one layer cannot silently reopen the hole.
    """
    from plugin.agent.actor import (
        RecordingMotor,
        brief_from_brain_choice,
        execute_actor,
        validate_brief,
    )
    from plugin.agent.capabilities.action_area import validate_actuation_grounding
    from plugin.agent.decision_consultation import _ground_choice_on_world
    from plugin.evals.golden.schema import load_all_cases
    from plugin.evals.golden.score import score_actor_case, score_brain_actor_handoff_case

    # 1) Every tagged high-cost action_area golden must exist and pass.
    min_cases = 5
    tagged = [
        c
        for cases in load_all_cases().values()
        for c in cases
        if "action_area" in (c.tags or []) and "high_cost" in (c.tags or [])
    ]
    if len(tagged) < min_cases:
        return False, f"need>={min_cases} action_area+high_cost goldens, got={len(tagged)}"
    scorers = {
        "actor": score_actor_case,
        "brain_actor_handoff": score_brain_actor_handoff_case,
    }
    fails: List[str] = []
    for case in tagged:
        scorer = scorers.get(case.module)
        if scorer is None:
            fails.append(f"{case.id}:no_scorer_for_{case.module}")
            continue
        result = scorer(case)
        if not result.passed:
            fails.append(case.id)
    if fails:
        return False, "golden_fail:" + ",".join(fails[:6])

    # 2) Inline e2e independent of JSONL: contact CTA + composer present,
    # filter also present → bind filter; motor into=Search; never contact point.
    world = {
        "surface": "conversation",
        "open_conversation": "Alice",
        "objects": [
            {"id": "filter_1", "kind": "search_field", "text": "Search", "point": [120, 80]},
            {
                "id": "row_alice",
                "kind": "contact",
                "text": "Alice",
                "matches_goal": True,
                "point": [800, 400],
            },
            {
                "id": "composer_1",
                "kind": "composer",
                "text": "Type a message",
                "point": [900, 900],
            },
        ],
    }
    grounded = _ground_choice_on_world(world, "compose_search_query", "Alice")
    if grounded.get("target_id") != "filter_1":
        return False, f"ground_choice latched {grounded.get('target_id')!r} not filter_1"
    if list(grounded.get("target_point") or []) != [120, 80]:
        return False, f"ground_choice point={grounded.get('target_point')}"

    brief = brief_from_brain_choice(
        {
            "family": "compose_search_query",
            "text": "query tokens",
            "target_label": "Alice",
            "target_id": "row_alice",
            "target_point": [800, 400],
            "coordinate_space": "screen",
        },
        world,
        app="GenericApp",
        allow_legacy_geometry=True,
    )
    ok, why = validate_brief(brief)
    if not ok:
        return False, f"handoff refused good filter bind: {why}"
    if brief.point != (120.0, 80.0):
        return False, f"handoff point={brief.point} (must be filter, not contact)"
    motor = RecordingMotor()
    outcome = execute_actor(brief, motor=motor)
    if not outcome.ok or not motor.calls:
        return False, f"execute failed on legal filter bind: {outcome.status}"
    into = str(motor.calls[0].get("into") or "")
    if into.lower() != "search":
        return False, f"motor into={into!r} (must be Search, never contact name)"

    # 3) Inline refuse: composer kind must not reach motor even with geometry.
    area_ok, area_why = validate_actuation_grounding(
        capability="compose_search_query",
        field_role="sidebar_search",
        label="Type a message",
        target_kind="composer",
    )
    if area_ok:
        return False, "validate_actuation_grounding allowed composer for filter type"
    refuse_motor = RecordingMotor()
    from plugin.agent.actor import ActorBrief

    refuse = execute_actor(
        ActorBrief(
            gesture="type",
            capability="compose_search_query",
            field_role="sidebar_search",
            label="Type a message",
            text="query tokens",
            point=(900.0, 900.0),
            target_kind="composer",
        ),
        motor=refuse_motor,
    )
    if refuse.ok or refuse_motor.calls:
        return False, "composer-kind brief reached motor"
    if "wrong_action_area" not in str(refuse.message or area_why):
        return False, f"refuse reason missing wrong_action_area: {refuse.message!r}"

    return True, f"action_area_high_cost_cases={len(tagged)}; e2e_bind+refuse_ok"


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
    Gate(
        "golden_v1_modules_pass",
        "Do perceive/critic/meta/brain/actor/handoff/reflect match frozen zarooratwala gold?",
        _golden_v1_modules_pass,
    ),
    Gate(
        "high_cost_wrong_action_area_impossible",
        "Can a high-cost type/commit land outside its action area (e.g. search query into chat)?",
        _high_cost_wrong_action_area_impossible,
    ),
    Gate(
        "storage_pressure_routes_to_housekeeping_capability",
        "Under storage-full, does meta chase goal search instead of housekeeping?",
        _storage_pressure_routes_to_housekeeping_capability,
    ),
    Gate(
        "prerequisite_intention_interrupts_on_blocking_condition",
        "Does a BlockingCondition spawn a prereq child and resume only after recheck?",
        _prerequisite_intention_interrupts_on_blocking_condition,
    ),
    Gate(
        "foreign_attempt_progress_does_not_verify_forward",
        "Can foreign-attempt / unscoped named effects verify Forward implications?",
        _foreign_attempt_progress_does_not_verify_forward,
    ),
    Gate(
        "foreign_result_plus_picker_does_not_bind_via_action",
        "Can stale last_result + ambient forward_picker latch source_object_selected via bind?",
        _foreign_result_plus_picker_does_not_bind_via_action,
    ),
    Gate(
        "open_conversation_sync_closes_open_source",
        "Does open_conversation=goal contact fail to close OPEN_SOURCE via real sync?",
        _open_conversation_sync_closes_open_source,
    ),
    Gate(
        "scoped_method_avoid_respects_world_signature",
        "Does point-free method avoid stick globally across world signature changes?",
        _scoped_method_avoid_respects_world_signature,
    ),
    Gate(
        "foreign_open_conversation_triggers_leave_before_compose",
        "Can foreign open CoE pane still compose_search instead of leave (145943)?",
        _foreign_open_conversation_triggers_leave_before_compose,
    ),
    Gate(
        "visible_source_chat_row_allows_open_despite_link_query",
        "Is actuatable Pallavi chat_row blocked by compose-first when link_query unpaid?",
        _visible_source_chat_row_allows_open_despite_link_query,
    ),
    Gate(
        "preclear_does_not_skip_when_list_with_foreign_pane",
        "Does harness preclear skip leave on LIST/SEARCH while foreign pane open?",
        _preclear_does_not_skip_when_list_with_foreign_pane,
    ),
    Gate(
        "search_type_regression_with_foreign_open_keeps_reach_source_leave_debt",
        "After search type regression under foreign open, does SEARCH still override leave?",
        _search_type_regression_with_foreign_open_keeps_reach_source_leave_debt,
    ),
    Gate(
        "identity_contract_does_not_block_matching_source_chat_row_open",
        "Does identity_contract refuse open_entity on matching Pallavi chat_row?",
        _identity_contract_does_not_block_matching_source_chat_row_open,
    ),
    Gate(
        "same_surface_different_container_reconsiders_method",
        "Does same-surface method avoid stick across semantic_container (Alice→Bob)?",
        _same_surface_different_container_reconsiders_method,
    ),
    Gate(
        "wrong_field_locus_forbids_type_when_composer_focused",
        "Can locate/type still run when composer is the focused locus?",
        _wrong_field_locus_forbids_type_when_composer_focused,
    ),
    Gate(
        "locate_effect_unknown_contracts",
        "Does AX-blind locate (ok+found=False) still allow same-method SEARCH replay (185549)?",
        _locate_effect_unknown_contracts,
    ),
    Gate(
        "native_find_does_not_type_when_only_composer_focused",
        "Does NativeFind type after Cmd+F no-op while composer holds focus?",
        _native_find_does_not_type_when_only_composer_focused,
    ),
    Gate(
        "wrong_container_locus_forbids_compose_into_foreign_open",
        "Does wrong-locus container forbid compose into foreign open?",
        _wrong_container_locus_forbids_compose_into_foreign_open,
    ),
    Gate(
        "empty_kind_high_cost_filter_fails_closed",
        "Do HIGH-cost filter writes pass with empty field_role/kind?",
        _empty_kind_high_cost_filter_fails_closed,
    ),
    Gate(
        "known_affordance_grounding_recovery_not_patient_substitute",
        "Does known-ungrounded Forward collapse to source bubble click (141617)?",
        _known_affordance_grounding_recovery_not_patient_substitute,
    ),
    Gate(
        "effect_absent_without_grounding_evidence_does_not_force_grounding",
        "Does effect-absent alone force GROUNDING class without hit evidence?",
        _effect_absent_without_grounding_evidence_does_not_force_grounding,
    ),
    Gate(
        "same_label_different_patient_does_not_satisfy_commitment",
        "Can Forward grounded on patient B clear commitment for patient A?",
        _same_label_different_patient_does_not_satisfy_commitment,
    ),
    Gate(
        "phenomenon_curriculum_hard_contracts",
        "Do live-seeded phenomenon goldens regress (warning/blocker/child/effect/resume)?",
        _phenomenon_curriculum_hard_contracts,
    ),
    Gate(
        "reveal_grounds_affordance_set_not_phash_skip",
        "After reveal_actions, can phash skip leave an empty affordance_set (112904)?",
        _reveal_grounds_affordance_set_not_phash_skip,
    ),
    Gate(
        "failed_reveal_escalates_off_context_click",
        "After motor-ok incomplete reveal, does OPEN_FORWARD re-context-click forever (153213)?",
        _failed_reveal_escalates_off_context_click,
    ),
    Gate(
        "effect_judgment_survives_meta_consume",
        "Does suppressed_rearm falsify effect-absent so motor escalate never runs (154356)?",
        _effect_judgment_survives_meta_consume,
    ),
    Gate(
        "content_probe_requires_referent_fit",
        "Can reveal/select bind a content entity that does not overlap goal referents (154356)?",
        _content_probe_requires_referent_fit,
    ),
    Gate(
        "overlay_capture_includes_menu_layer_after_reveal",
        "After reveal, does window-scoped capture still omit context-menu layers (150708)?",
        _overlay_capture_includes_menu_layer_after_reveal,
    ),
    Gate(
        "post_accept_promote_and_multipass_explore",
        "After reveal, does promote miss the accepted menu doc / skip multipass relook (235701)?",
        _post_accept_promote_and_multipass_explore,
    ),
    Gate(
        "ax_search_binds_compose_without_vlm_object",
        "Does compose demote when AX Q Search exists but VLM objects are only chat rows (123746)?",
        _ax_search_binds_compose_without_vlm_object,
    ),
    Gate(
        "reveal_geometry_mismatch_prefers_landed_not_intended",
        "After reveal geometry mismatch, does reflect retry the failed intended latch (125715)?",
        _reveal_geometry_mismatch_prefers_landed_not_intended,
    ),
    Gate(
        "search_results_do_not_observe_thrash",
        "On search with a unique fitting row, do reveal/observe collapse to Observe thrash (131221)?",
        _search_results_do_not_observe_thrash,
    ),
    Gate(
        "search_ranks_before_open_on_ambiguous",
        "On multi-hit search, does the agent open a query-echo instead of ranking (160112/160317)?",
        _search_ranks_before_open_on_ambiguous,
    ),
    Gate(
        "meta_search_owns_find_among_many",
        "Is find-among-many still an ACT catalog verb instead of MetaAction.SEARCH?",
        _meta_search_owns_find_among_many,
    ),
    Gate(
        "find_outcome_seam_never_leaves_ranking",
        "After resolve abstain or open miss, can the episode stay ranking and re-SEARCH (213012)?",
        _find_outcome_seam_never_leaves_ranking,
    ),
    Gate(
        "stale_compose_search_does_not_arm_retreat",
        "Does a stale/foreground refuse on compose_search arm search_retreat and block SEARCH (202457)?",
        _stale_compose_search_does_not_arm_retreat,
    ),
    Gate(
        "entity_resolution_search_owns_meta_and_type_query",
        "Does unresolved searchable destination still fall through to Observe/ACT instead of SEARCH→type_query (203259)?",
        _entity_resolution_search_owns_meta_and_type_query,
    ),
    Gate(
        "search_evidence_owns_surface_and_resolve_recovery",
        "Can conversation patch override search evidence, or resolve claim open, or decline Observe-thrash after resolve (210526)?",
        _search_evidence_owns_surface_and_resolve_recovery,
    ),
    Gate(
        "source_query_binding_rejects_distractor_urls",
        "Can YouTube/generic URL in Pallavi bind or reveal as zarooratwala source_object (214025)?",
        _source_query_binding_rejects_distractor_urls,
    ),
    Gate(
        "typed_role_binding_identity_gates",
        "Can high task-relevance bind a role without satisfying its identity contract (230407 brand row / YouTube preview)?",
        _typed_role_binding_identity_gates,
    ),
    Gate(
        "coordinate_frame_roundtrip_and_typed_actuators",
        "Do coordinate frames, coverage split, typed chords, and attempt validity hold (143550 grounding chain)?",
        _coordinate_frame_roundtrip_and_typed_actuators,
    ),
    Gate(
        "core_generalization_gate",
        "Do generic binder/grounder/executive modules import WhatsApp/Gmail/Finder or task-specific names?",
        _core_generalization_gate,
    ),
    Gate(
        "typed_action_and_untyped_geometry_gate",
        "Can a production act click without CapabilityRef/Grounding, or free-text chords become clicks?",
        _typed_action_and_untyped_geometry_gate,
    ),
    Gate(
        "wrong_selection_reverts_not_forwards",
        "On goal-inconsistent multi-select (132831), does the agent follow toolbar Forward instead of revert_effects?",
        _wrong_selection_reverts_not_forwards,
    ),
    Gate(
        "barren_filter_chip_backtracks_not_ig_thrash",
        "On typed filter_chip barren search while hunting a link, does the agent IG/THINK thrash instead of backtrack/revert?",
        _barren_filter_chip_backtracks_not_ig_thrash,
    ),
    Gate(
        "recoverability_substrate_wired_for_goldens",
        "Is the agent missing structure/behavior (aliases, fitness, meta, undo, brain) that recoverability goldens require?",
        _recoverability_substrate_wired_for_goldens,
    ),
    Gate(
        "text_compose_author_never_uses_vision_task",
        "Can text-only query authorship ride the vision perception pin?",
        _text_compose_author_never_uses_vision_task,
    ),
    Gate(
        "llm_meta_choice_never_acts_while_look_owed",
        "Can LLM meta choose ACT while post-act re-perceive is unpaid?",
        _llm_meta_choice_never_acts_while_look_owed,
    ),
    Gate(
        "meta_packet_shaped_from_live_situations",
        "Is the meta LLM packet missing mined live-situation sections?",
        _meta_packet_shaped_from_live_situations,
    ),
    Gate(
        "invoke_requires_referent_selection",
        "Can object-scoped invoke_affordance run without a matching selected referent (235148)?",
        _invoke_requires_referent_selection,
    ),
    Gate(
        "referent_repair_owed_forces_act_not_explore",
        "After invoke wrong-target regression, does meta EXPLORE thrash instead of ACT repair?",
        _referent_repair_owed_forces_act_not_explore,
    ),
    Gate(
        "selection_mode_not_context_menu",
        "Does 'N Selected' toolbar chrome stay mislabeled as context_menu?",
        _selection_mode_not_context_menu,
    ),
    Gate(
        "act_clear_stops_route_explore_latch",
        "After Forward is clear on an open menu, does sticky route debt still force EXPLORE (001141)?",
        _act_clear_stops_route_explore_latch,
    ),
    Gate(
        "failed_reveal_episode_frees_meta_from_explore",
        "After motor-ok empty reveal TTL, does sticky incomplete still force EXPLORE forever (142848)?",
        _failed_reveal_episode_frees_meta_from_explore,
    ),
    Gate(
        "intention_frame_survives_method_miss",
        "Does METHOD_INEFFECTIVE drop the EXPLORE intention and allow Observe thrash (181059)?",
        _intention_frame_survives_method_miss,
    ),
    Gate(
        "child_prereq_spawn_resume_reranks",
        "Does PRECONDITION_MISSING skip child spawn, or resume blind-replay the blocked method?",
        _child_prereq_spawn_resume_reranks,
    ),
    Gate(
        "forward_picker_requires_destination_before_forward",
        "On Send-to, can Forward commit without inventory-selected destination (184742 safety)?",
        _forward_picker_requires_destination_before_forward,
    ),
    Gate(
        "surface_ownership_blocks_cross_surface_destination",
        "Can background selection ownership satisfy destination_selected / skip SEARCH (184742)?",
        _surface_ownership_blocks_cross_surface_destination,
    ),
    Gate(
        "semantic_perception_zero_cross_surface_contamination",
        "Does the semantic perception harness allow cross-surface selection contamination (184742 family)?",
        _semantic_perception_zero_cross_surface_contamination,
    ),
    Gate(
        "act_clear_requires_control_geometry",
        "Can label-only menu Forward (no point/bounds) still claim act_clear (171627)?",
        _act_clear_requires_control_geometry,
    ),
    Gate(
        "act_clear_act_rejects_observe",
        "Under act_clear+ACT, can Observe/Escape/reveal still sanitize through (171627)?",
        _act_clear_act_rejects_observe,
    ),
    Gate(
        "overlay_invoke_binds_menu_geometry_not_content",
        "Does overlay Forward invoke bind menu geometry, or click the content URL?",
        _overlay_invoke_binds_menu_geometry_not_content,
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
