"""Evaluate the multimodal perceptor on real recorded scenes.

Frames are recorded during a live run (``HERMES_PERCEPTOR_RECORD_DIR``), so the
eval replays genuine scenes from a genuine flow without needing the GUI, the
app, or a particular screen state to be present when it runs.

Three things are scored, because a perceptor can fail at any of them
independently:

1. **Input contract** -- did the model actually receive usable multimodal
   input? A blank screenshot or an AX list with no ids means the rest of the
   score is meaningless.
2. **Scene representation** -- is the structured reading well-formed,
   canonical, and *actionable*? A confident reading that names no target
   cannot be executed, which is a silent failure mode.
3. **Summary quality** -- is there a human-readable sentence, and does it
   agree with the structured reading it accompanies?

Usage:
    # score the responses captured during the run
    python -m plugin.experiments.perceptor_eval --frames <dir>

    # re-ask the model about the same scenes (fresh, comparable, offline GUI)
    python -m plugin.experiments.perceptor_eval --frames <dir> --live
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from plugin.agent.unified_cognition import (  # noqa: E402
    ALLOWED_ACTIONS,
    UnifiedProposal,
    _parse_proposal,
)

DEFAULT_FRAMES = Path("plugin/experiments/fixtures/perceptor/live_forward")

# A perceptor whose surface label drifts every frame cannot drive a state
# machine, so free-text labels are folded onto a canonical vocabulary and
# anything that will not fold is counted as a miss.
CANONICAL_SURFACES: Dict[str, Tuple[str, ...]] = {
    "chat_list": ("chat list", "chats list", "main window", "conversation list", "sidebar", "home"),
    "conversation": ("conversation", "chat view", "chat window", "message thread", "thread"),
    "search": ("search", "search results", "search bar focused"),
    "context_menu": ("context menu", "message menu", "right click menu"),
    "forward_picker": ("forward", "destination picker", "share sheet", "recipient picker"),
    "dialog": ("dialog", "modal", "alert", "permission"),
    "blank": ("blank", "black", "loading", "empty", "unknown"),
}

_MIN_SUMMARY_CHARS = 40
_MAX_SUMMARY_CHARS = 600
# Below this mean luminance a frame is effectively black: nothing to perceive.
_MIN_MEAN_LUMA = 8.0


def canonical_surface(raw: str) -> str:
    """Fold a free-text surface label onto the canonical vocabulary."""
    text = str(raw or "").strip().lower().replace("_", " ")
    if not text:
        return ""
    for canon, phrases in CANONICAL_SURFACES.items():
        if text == canon.replace("_", " "):
            return canon
        for phrase in phrases:
            if phrase in text:
                return canon
    return ""


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class FrameScore:
    frame: str
    input_checks: List[Check] = field(default_factory=list)
    scene_checks: List[Check] = field(default_factory=list)
    summary_checks: List[Check] = field(default_factory=list)
    action_checks: List[Check] = field(default_factory=list)
    world_checks: List[Check] = field(default_factory=list)
    capability_checks: List[Check] = field(default_factory=list)
    surface_raw: str = ""
    surface_canonical: str = ""
    summary: str = ""
    # Which verb the model reached for. A reading can score perfectly on every
    # representational metric and still pick a strategy whose depth is the
    # length of the history, which no amount of accuracy rescues.
    action_family: str = ""
    latency_s: float = 0.0
    model: str = ""

    def _rate(self, checks: List[Check]) -> float:
        return round(sum(1 for c in checks if c.passed) / len(checks), 4) if checks else 0.0

    @property
    def input_score(self) -> float:
        return self._rate(self.input_checks)

    @property
    def scene_score(self) -> float:
        return self._rate(self.scene_checks)

    @property
    def summary_score(self) -> float:
        return self._rate(self.summary_checks)

    @property
    def action_score(self) -> float:
        return self._rate(self.action_checks)

    @property
    def world_score(self) -> float:
        return self._rate(self.world_checks)

    @property
    def capability_score(self) -> float:
        return self._rate(self.capability_checks)

    def failures(self) -> List[str]:
        return [
            f"{c.name}: {c.detail}"
            for c in (
                *self.input_checks,
                *self.scene_checks,
                *self.summary_checks,
                *self.action_checks,
                *self.world_checks,
                *self.capability_checks,
            )
            if not c.passed
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame": self.frame,
            "model": self.model,
            "latency_s": round(self.latency_s, 3),
            "surface_raw": self.surface_raw,
            "surface_canonical": self.surface_canonical,
            "action_family": self.action_family,
            "summary": self.summary,
            "scores": {
                "input_contract": self.input_score,
                "scene_representation": self.scene_score,
                "summary_quality": self.summary_score,
                "actionability": self.action_score,
                "world_update": self.world_score,
                "capability_choice": self.capability_score,
            },
            "checks": {
                "input": [c.to_dict() for c in self.input_checks],
                "scene": [c.to_dict() for c in self.scene_checks],
                "summary": [c.to_dict() for c in self.summary_checks],
                "action": [c.to_dict() for c in self.action_checks],
                "world": [c.to_dict() for c in self.world_checks],
                "capability": [c.to_dict() for c in self.capability_checks],
            },
            "failures": self.failures(),
        }


def _image_stats(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {"present": False}
    try:
        from PIL import Image, ImageStat

        with Image.open(path) as image:
            grey = image.convert("L")
            stat = ImageStat.Stat(grey)
            return {
                "present": True,
                "size": list(image.size),
                "mean_luma": round(stat.mean[0], 2),
                "stddev_luma": round(stat.stddev[0], 2),
                "bytes": path.stat().st_size,
            }
    except Exception as exc:
        return {"present": True, "error": str(exc)}


def packet_observation(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Frames recorded before the world document used a different key."""
    observation = packet.get("observation")
    if not isinstance(observation, dict):
        observation = packet.get("current_observation")
    return observation if isinstance(observation, dict) else {}


def score_input_contract(packet: Dict[str, Any], image: Dict[str, Any]) -> List[Check]:
    """Did the perceptor receive usable multimodal input?"""
    checks: List[Check] = []
    observation = packet_observation(packet)
    evidence = observation.get("ax_evidence") or []

    checks.append(Check("packet_has_goal", bool(packet.get("goal", {}).get("operation")),
                        str(packet.get("goal"))[:80]))
    # The model's own prior world must come back to it, and the runtime's
    # AX-derived guess must not: recomputing the world every cycle is what
    # discarded beliefs between steps.
    checks.append(Check("packet_carries_prior_world", isinstance(packet.get("world_model"), dict),
                        str(packet.get("world_model"))[:80]))
    checks.append(Check("packet_has_no_runtime_task_state", "task_state" not in packet))
    checks.append(Check("packet_has_observation", bool(observation)))
    checks.append(Check(
        "allowed_actions_declared",
        set(packet.get("allowed_actions") or []) == set(ALLOWED_ACTIONS),
        str(packet.get("allowed_actions"))[:120],
    ))
    checks.append(Check("screenshot_present", bool(image.get("present")), json.dumps(image)[:120]))

    luma = image.get("mean_luma")
    checks.append(Check(
        "screenshot_not_blank",
        isinstance(luma, (int, float)) and float(luma) >= _MIN_MEAN_LUMA,
        f"mean_luma={luma}",
    ))
    checks.append(Check(
        "screenshot_has_detail",
        isinstance(image.get("stddev_luma"), (int, float)) and float(image["stddev_luma"]) > 1.0,
        f"stddev={image.get('stddev_luma')}",
    ))
    # AX may legitimately be empty (Electron apps publish almost nothing), but
    # whatever is offered must be addressable: an entry without an id can never
    # be turned back into a click target.
    ids_ok = all("id" in item for item in evidence)
    checks.append(Check("ax_evidence_entries_have_ids", ids_ok, f"n={len(evidence)}"))
    bounded = [item for item in evidence if item.get("bounds")]
    checks.append(Check(
        "ax_evidence_bounds_present_when_available",
        not evidence or bool(bounded) or all(not item.get("bounds") for item in evidence),
        f"{len(bounded)}/{len(evidence)} carry bounds",
    ))
    blob = json.dumps(packet)
    checks.append(Check("no_credentials_in_packet",
                        not re.search(r"(api[_-]?key|authorization|bearer\s)", blob, re.I)))
    return checks


def score_scene_representation(proposal: UnifiedProposal, packet: Dict[str, Any]) -> List[Check]:
    """Is the structured reading well-formed, canonical, and actionable?"""
    checks: List[Check] = []
    state = proposal.observed_state or {}
    action = proposal.next_action or {}

    checks.append(Check("has_observed_state", bool(state), str(state)[:100]))
    surface_raw = str(state.get("surface") or "")
    checks.append(Check("surface_reported", bool(surface_raw.strip()), surface_raw))
    canon = canonical_surface(surface_raw)
    checks.append(Check("surface_is_canonical", bool(canon), f"{surface_raw!r} -> {canon or 'UNMAPPED'}"))
    checks.append(Check(
        "target_visibility_is_boolean",
        isinstance(state.get("target_object_visible"), bool),
        repr(state.get("target_object_visible")),
    ))

    family = str(action.get("family") or "").strip().lower()
    checks.append(Check("action_proposed", bool(family), family))
    checks.append(Check("action_in_allowed_set", family in ALLOWED_ACTIONS, family))

    # The failure that matters most in practice: a confident pointer / entity
    # capability naming nothing the runtime can click.
    pointer = family in {
        "click",
        "right_click",
        "hover",
        "open_entity",
        "select_content",
        "reveal_actions",
    }
    grounded = (
        action.get("target_id") not in (None, "")
        or bool(action.get("target_point"))
        or bool(str(action.get("target_label") or action.get("text") or "").strip())
    )
    checks.append(Check(
        "pointer_action_is_grounded",
        (not pointer) or grounded,
        f"family={family} target_id={action.get('target_id')} point={action.get('target_point')}",
    ))

    confidence = proposal.confidence
    checks.append(Check("confidence_in_range", 0.0 <= float(confidence or 0.0) <= 1.0, str(confidence)))

    beliefs = proposal.belief_updates or []
    well_formed = all(
        str(b.get("predicate") or "").strip() and 0.0 <= float(b.get("confidence") or 0.0) <= 1.0
        for b in beliefs
    )
    checks.append(Check("belief_updates_well_formed", well_formed, f"n={len(beliefs)}"))
    checks.append(Check("belief_updates_cite_evidence",
                        all(b.get("evidence") for b in beliefs) if beliefs else True))

    # Forgetting which conversation is open while still reading the screen as a
    # conversation is the amnesia that made the agent undo its own progress.
    prior = packet.get("world_model") if isinstance(packet.get("world_model"), dict) else {}
    prior_conv = str(prior.get("open_conversation") or "").strip()
    observed_conv = str(state.get("open_conversation") or "").strip()
    forgot = bool(prior_conv) and not observed_conv and canon == "conversation"
    checks.append(Check("open_conversation_not_silently_dropped", not forgot,
                        f"prior={prior_conv!r} now={observed_conv!r}"))
    return checks


def score_world_update(proposal: UnifiedProposal, packet: Dict[str, Any]) -> List[Check]:
    """Is the returned world usable as the next call's input?

    The document is the agent's only memory between steps, so a malformed or
    unprovenanced one degrades every later frame rather than just this one.
    """
    from plugin.agent.world_document import MAX_BELIEFS, MAX_OBJECTS

    checks: List[Check] = []
    document = proposal.world_model or {}
    checks.append(Check("world_document_returned", bool(document), str(document)[:100]))

    objects = [o for o in (document.get("objects") or []) if isinstance(o, dict)]
    beliefs = [b for b in (document.get("beliefs") or []) if isinstance(b, dict)]

    checks.append(Check(
        "objects_are_addressable",
        all(o.get("point") or o.get("id") for o in objects),
        f"n={len(objects)}",
    ))
    checks.append(Check(
        "beliefs_carry_evidence",
        all(b.get("evidence") for b in beliefs),
        f"n={len(beliefs)}",
    ))
    checks.append(Check(
        "beliefs_carry_frame_stamps",
        all(isinstance(b.get("confirmed_on_frame"), int) for b in beliefs),
        f"n={len(beliefs)}",
    ))
    progress = document.get("progress") or {}
    checks.append(Check(
        "progress_is_tracked",
        bool(str(progress.get("phase") or "").strip() or str(progress.get("objective") or "").strip()),
        str(progress)[:80],
    ))
    checks.append(Check(
        "document_within_bounds",
        len(objects) <= MAX_OBJECTS and len(beliefs) <= MAX_BELIEFS,
        f"objects={len(objects)} beliefs={len(beliefs)}",
    ))

    # The confabulation guard, measured rather than enforced: a belief the
    # runtime flagged as unconfirmed must be reconfirmed against this frame or
    # dropped, never carried forward untouched.
    flagged = [str(item).split(" (")[0] for item in (packet.get("unconfirmed_beliefs") or [])]
    frame = int((packet_observation(packet) or {}).get("frame") or 0)
    carried = [
        b.get("predicate")
        for b in beliefs
        if b.get("predicate") in flagged and int(b.get("confirmed_on_frame") or 0) < frame
    ]
    checks.append(Check(
        "stale_beliefs_reconfirmed_or_dropped",
        not carried,
        f"carried_untouched={carried}" if carried else f"flagged={len(flagged)}",
    ))
    return checks


def score_summary(proposal: UnifiedProposal) -> List[Check]:
    """Is there a readable sentence, and does it match the structured reading?"""
    checks: List[Check] = []
    summary = (proposal.scene_summary or "").strip()
    checks.append(Check("summary_present", bool(summary), summary[:80]))
    checks.append(Check("summary_long_enough", len(summary) >= _MIN_SUMMARY_CHARS, f"{len(summary)} chars"))
    checks.append(Check("summary_not_bloated", len(summary) <= _MAX_SUMMARY_CHARS, f"{len(summary)} chars"))
    checks.append(Check("summary_is_prose", bool(re.search(r"[a-z]\s+[a-z]", summary, re.I)) and "{" not in summary,
                        summary[:80]))
    checks.append(Check("summary_has_no_base64", "base64" not in summary.lower() and
                        not re.search(r"[A-Za-z0-9+/]{80,}", summary)))

    state = proposal.observed_state or {}
    lowered = summary.lower()
    # Prose that claims an open conversation while the structure says none is
    # the boundary inconsistency the unified design exists to prevent.
    claims_open = bool(re.search(r"\b(conversation|chat)\b[^.]{0,40}\b(is )?(open|selected)\b", lowered)) and \
        not re.search(r"\b(no|not|none)\b[^.]{0,30}\b(conversation|chat)\b", lowered)
    structure_open = bool(str(state.get("open_conversation") or "").strip())
    checks.append(Check(
        "summary_agrees_with_structure",
        not (claims_open and not structure_open),
        f"prose_claims_open={claims_open} structure_open={structure_open}",
    ))
    return checks


def score_actionability(proposal: UnifiedProposal, packet: Dict[str, Any]) -> List[Check]:
    """Would the runtime actually execute this reading?

    A perceptor can score perfectly on every representational metric and still
    leave the agent looping, because the reading is rejected by the runtime's
    admissibility or escalation gates. This runs the real gates so that gap is
    measured here instead of during a multi-minute live run.
    """
    from plugin.agent.goal import Goal
    from plugin.agent.features import StateFeatures
    from plugin.agent.unified_cognition import proposal_to_action, should_escalate
    from plugin.worldmodel.model import WorldModel

    checks: List[Check] = []
    goal_spec = packet.get("goal") or {}
    goal = Goal(
        kind=str(goal_spec.get("operation") or "whatsapp_forward_message"),
        contact=str(goal_spec.get("source_conversation") or ""),
        target_contact=str(goal_spec.get("destination") or ""),
        link_query=str(goal_spec.get("source_query") or ""),
    )

    # Rebuild just enough world for id resolution; entities the perceptor
    # referenced by id must exist for the action to bind.
    world = WorldModel(active_app=str(packet_observation(packet).get("app") or ""))
    action, reason = proposal_to_action(proposal, goal, world)

    declined = reason.startswith("model_requested_")
    checks.append(Check("reading_is_admissible", action is not None or declined, reason))

    features = StateFeatures(extras={})
    escalate, escalate_reason = should_escalate(proposal, features, admissible=action is not None)
    checks.append(Check(
        "fast_path_accepts_reading",
        (action is not None and not escalate) or declined,
        f"admissibility={reason} escalate={escalate}({escalate_reason})",
    ))
    # Scrolling and keyboard families are executed against a computed anchor or
    # the focused element, so requiring a target for them would flag correct
    # behaviour.
    from plugin.agent.unified_cognition import _KEYBOARD_FAMILIES

    family = str((proposal.next_action or {}).get("family") or "").strip().lower()
    needs_target = family not in _KEYBOARD_FAMILIES and family not in {"scroll", "observe"}
    checks.append(Check(
        "action_is_executable",
        action is None
        or not needs_target
        or bool(action.target_entity_id or action.target_point or action.semantic_target or action.text),
        "" if action is None else f"family={family} entity={action.target_entity_id} "
                                  f"point={action.target_point} text={action.text!r}",
    ))
    return checks


def load_frames(directory: Path) -> List[Dict[str, Any]]:
    frames = []
    for path in sorted(directory.glob("frame_*.json")):
        try:
            frames.append({"path": path, "data": json.loads(path.read_text())})
        except Exception as exc:
            print(f"skipping unreadable frame {path.name}: {exc}")
    return frames


def _apply_run_defaults() -> None:
    """Score against the same models and timeout the live run uses.

    Without this the eval silently falls back to the generic default chain and
    a 15s timeout, so every frame 'fails' for reasons the agent would never
    hit, which makes the scores worse than useless.
    """
    defaults = {
        "HERMES_SCREEN_UNDERSTANDING_MODEL": "qwen3.5:397b",
        "HERMES_SCREEN_UNDERSTANDING_PROVIDER": "ollama-cloud",
        "HERMES_SCREEN_UNDERSTANDING_FALLBACK_CHAIN": '[{"provider":"ollama-cloud","model":"gemma4:31b"}]',
        "HERMES_PERCEPTION_LLM_TIMEOUT_SECONDS": "90",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def _replay_live(packet: Dict[str, Any], image_path: Optional[Path]) -> Tuple[Optional[UnifiedProposal], float]:
    """Re-ask the model about a recorded scene."""
    from plugin.agent.perception_synthesis import (
        _call_llm_hard_timeout,
        _main_runtime_snapshot,
        _perception_extra_body,
        _perception_max_tokens,
        _perception_reasoning_config,
        _perception_task_targets,
        _perception_timeout_seconds,
    )
    from plugin.agent.reasoning_consultation import consult_reasoning
    from plugin.agent.unified_cognition import UNIFIED_TASK, _build_messages

    messages, _image_size = _build_messages(packet, str(image_path) if image_path else "")
    main_runtime = _main_runtime_snapshot()
    timeout_s = _perception_timeout_seconds()
    for target in _perception_task_targets(main_runtime, task_name=UNIFIED_TASK):
        start = time.time()
        try:
            consultation = consult_reasoning(
                UNIFIED_TASK,
                messages,
                caller=lambda **kwargs: _call_llm_hard_timeout(timeout_s, **kwargs),
                call_kwargs={
                    "task": UNIFIED_TASK,
                    "provider": target.get("provider") or None,
                    "model": target.get("model") or None,
                    "base_url": target.get("base_url") or None,
                    "api_key": target.get("api_key") or None,
                    "timeout": timeout_s,
                    "main_runtime": main_runtime,
                    "extra_body": _perception_extra_body(main_runtime),
                    "reasoning_config": _perception_reasoning_config(target),
                },
                temperature=0.0,
                max_tokens=max(512, _perception_max_tokens()),
            )
        except Exception as exc:
            print(f"   live replay failed on {target.get('model')}: {str(exc)[:100]}")
            continue
        if not consultation.parsed:
            continue
        proposal = _parse_proposal(consultation.parsed)
        proposal.model = str(target.get("model") or "")
        proposal.latency_s = time.time() - start
        return proposal, proposal.latency_s
    return None, 0.0


def evaluate(directory: Path, *, live: bool = False, limit: int = 0, since: int = 0) -> Dict[str, Any]:
    frames = load_frames(directory)
    if since:
        # Frames accumulate across runs, so scoring a slice is how a change is
        # compared against the behaviour that preceded it.
        frames = [f for f in frames if int(f["data"].get("frame") or 0) >= since]
    if limit:
        frames = frames[:limit]
    if not frames:
        raise SystemExit(f"no recorded frames in {directory} — run the flow with HERMES_PERCEPTOR_RECORD_DIR set")

    if live:
        _apply_run_defaults()

    scores: List[FrameScore] = []
    for entry in frames:
        path, data = entry["path"], entry["data"]
        packet = data.get("packet") or {}
        image_name = data.get("screenshot") or ""
        image_path = (directory / image_name) if image_name else None
        image = _image_stats(image_path)

        # Score against today's vocabulary even for old recordings: otherwise
        # every historical frame fails allowed_actions_declared the moment the
        # catalog grows, which hides real composition defects.
        packet = {**packet, "allowed_actions": list(ALLOWED_ACTIONS)}

        if live:
            proposal, _ = _replay_live(packet, image_path)
        else:
            recorded = data.get("response")
            proposal = _parse_proposal(recorded) if isinstance(recorded, dict) else None
            if proposal is not None and isinstance(recorded, dict):
                proposal.model = str(recorded.get("model") or "")
                proposal.latency_s = float(recorded.get("latency_s") or 0.0)
                proposal.scene_summary = str(recorded.get("scene_summary") or "").strip()

        score = FrameScore(frame=path.stem)
        score.input_checks = score_input_contract(packet, image)
        if proposal is None:
            score.scene_checks = [Check("model_returned_a_reading", False, "no parseable response")]
            score.summary_checks = [Check("summary_present", False, "no response")]
            score.action_checks = [Check("fast_path_accepts_reading", False, "no response")]
            score.world_checks = [Check("world_document_returned", False, "no response")]
            score.capability_checks = [Check("action_family_present", False, "no response")]
        else:
            from plugin.experiments.capability_eval import (
                score_capability_choice,
                score_capability_gates,
            )

            score.scene_checks = score_scene_representation(proposal, packet)
            score.summary_checks = score_summary(proposal)
            score.action_checks = score_actionability(proposal, packet)
            score.world_checks = score_world_update(proposal, packet)
            # Composition fitness: right family for the substrate, not just a
            # parseable family. This is what vocabulary-membership tests miss.
            score.capability_checks = score_capability_choice(proposal, packet) + score_capability_gates(
                proposal, packet
            )
            score.surface_raw = str((proposal.observed_state or {}).get("surface") or "")
            score.surface_canonical = canonical_surface(score.surface_raw)
            score.summary = proposal.scene_summary
            score.action_family = str((proposal.next_action or {}).get("family") or "")
            score.latency_s = proposal.latency_s
            score.model = proposal.model
        scores.append(score)

    return _aggregate(scores, directory=directory, live=live)


def _aggregate(scores: List[FrameScore], *, directory: Path, live: bool) -> Dict[str, Any]:
    def mean(values: List[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    canonical_hits = [s for s in scores if s.surface_canonical]
    distinct_labels = sorted({s.surface_raw for s in scores if s.surface_raw})
    distinct_canonical = sorted({s.surface_canonical for s in canonical_hits})

    # Frames from one flow over a static screen should not produce a new
    # surface name each time; label churn is a measurable defect.
    stability = round(len(distinct_canonical) / max(1, len(distinct_labels)), 4)

    failure_counts: Dict[str, int] = {}
    for score in scores:
        for failure in score.failures():
            failure_counts[failure.split(":")[0]] = failure_counts.get(failure.split(":")[0], 0) + 1

    return {
        "frames_dir": str(directory),
        "mode": "live_replay" if live else "recorded",
        "frame_count": len(scores),
        "scores": {
            "input_contract": mean([s.input_score for s in scores]),
            "scene_representation": mean([s.scene_score for s in scores]),
            "summary_quality": mean([s.summary_score for s in scores]),
            "actionability": mean([s.action_score for s in scores]),
            "world_update": mean([s.world_score for s in scores]),
            "capability_choice": mean([s.capability_score for s in scores]),
        },
        "surface_labels": {
            "distinct_raw": distinct_labels,
            "distinct_canonical": distinct_canonical,
            "canonical_rate": mean([1.0 if s.surface_canonical else 0.0 for s in scores]),
            "label_stability": stability,
        },
        "mean_latency_s": mean([s.latency_s for s in scores]),
        "action_families": dict(
            sorted(Counter(s.action_family for s in scores if s.action_family).items(), key=lambda kv: -kv[1])
        ),
        "failures_by_check": dict(sorted(failure_counts.items(), key=lambda kv: -kv[1])),
        "frames": [s.to_dict() for s in scores],
    }


def render_report(report: Dict[str, Any]) -> str:
    lines = [
        f"Perceptor eval — {report['frame_count']} frames ({report['mode']}) from {report['frames_dir']}",
        "",
        f"  input contract       {report['scores']['input_contract']:.2%}",
        f"  scene representation {report['scores']['scene_representation']:.2%}",
        f"  summary quality      {report['scores']['summary_quality']:.2%}",
        f"  actionability        {report['scores']['actionability']:.2%}",
        f"  world update         {report['scores']['world_update']:.2%}",
        f"  capability choice    {report['scores'].get('capability_choice', 0):.2%}",
        "",
        f"  surface canonical rate {report['surface_labels']['canonical_rate']:.2%}"
        f"  label stability {report['surface_labels']['label_stability']:.2f}",
        f"  distinct raw labels: {report['surface_labels']['distinct_raw']}",
        f"  mean latency: {report['mean_latency_s']:.2f}s",
        f"  chosen actions: {report['action_families'] or '{}'}",
    ]
    if report["failures_by_check"]:
        lines += ["", "  failing checks (frames affected):"]
        for name, count in report["failures_by_check"].items():
            lines.append(f"    {count:3d}x {name}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, default=DEFAULT_FRAMES)
    parser.add_argument("--live", action="store_true", help="re-ask the model about each recorded scene")
    parser.add_argument("--limit", type=int, default=0, help="only score the first N frames")
    parser.add_argument("--since", type=int, default=0, help="only score frames numbered >= N")
    parser.add_argument("--json", type=Path, default=None, help="write the full report here")
    parser.add_argument(
        "--capability-scenarios",
        action="store_true",
        help="also run the forward-composition scenario suite (no GUI)",
    )
    parser.add_argument(
        "--world-critic-scenarios",
        action="store_true",
        help="run world-critic high-level representation update suite (no GUI)",
    )
    args = parser.parse_args()

    report = evaluate(args.frames, live=args.live, limit=args.limit, since=args.since)
    print(render_report(report))
    if args.capability_scenarios:
        from plugin.experiments.capability_eval import (
            evaluate_forward_scenarios,
            evaluate_forward_trajectories,
        )

        scenarios = evaluate_forward_scenarios()
        trajectories = evaluate_forward_trajectories()
        report["capability_scenarios"] = scenarios
        report["capability_trajectories"] = trajectories
        print(
            f"\nCapability scenarios — {scenarios['passed']}/{scenarios['scenario_count']} passed"
            + (f"  failed: {scenarios['failed']}" if scenarios["failed"] else "")
        )
        print(
            f"Capability trajectories — {trajectories['passed']}/{trajectories['trajectory_count']} passed"
            + (f"  failed: {trajectories['failed']}" if trajectories["failed"] else "")
        )
    if args.world_critic_scenarios:
        from plugin.experiments.world_critic_eval import (
            evaluate_world_critic_scenarios,
            evaluate_world_critic_trajectories,
            render_report as render_critic_report,
        )

        wc_scenarios = evaluate_world_critic_scenarios()
        wc_trajectories = evaluate_world_critic_trajectories()
        report["world_critic_scenarios"] = wc_scenarios
        report["world_critic_trajectories"] = wc_trajectories
        print("\n" + render_critic_report(wc_scenarios, wc_trajectories))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nfull report: {args.json}")
    failed = bool(
        (
            args.capability_scenarios
            and (
                report.get("capability_scenarios", {}).get("failed")
                or report.get("capability_trajectories", {}).get("failed")
            )
        )
        or (
            args.world_critic_scenarios
            and (
                report.get("world_critic_scenarios", {}).get("failed")
                or report.get("world_critic_trajectories", {}).get("failed")
            )
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
