"""Piecewise post-open pipeline eval (perceive → critic → brain).

General loop under test (WhatsApp / zarooratwala is one fixture trajectory):

    perceive any surface
      → critic accepts Δworld
      → brain chooses a capability
      → actuators ground by geometry / AX (no app folklore)

Live stall pattern this isolates:

  open_entity click succeeded, but AX still echoed search chrome as
  ``open_conversation``; transition scored regression; executive stayed in
  verify/think; brain never chose locate_content.

Pieces (each scored independently so a single failure names the layer):

  A  Perception — multimodal reading names conversation + open contact
  B  Critic     — accepts that reading after open_entity; refuses search chrome
  C  Brain      — on accepted conversation with content not visible → locate_content
  D  AX trap    — AX open title is search chrome; critic still keeps the contact

Offline uses recorded fixture replies. ``--live`` re-asks a real perceptor on
the frozen screenshot + packet (same path as ``plugin.evals.fusion``).

Usage:
    python -m plugin.evals.post_open_pipeline
    python -m plugin.evals.post_open_pipeline --live --model ollama-cloud/qwen3.5:397b
    python -m plugin.evals.run   # includes [post_open_pipeline] block
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from plugin.evals.annotations import annotate, load_overrides
from plugin.evals.corpus import DEFAULT_CORPUS_DIR, DEFAULT_RECORD_DIR, Fixture, load_fixtures
from plugin.evals.fusion import (
    _proposal_from_response,
    resolve_screenshot,
    replay_on_model,
    score_fusion_reading,
)
from plugin.evals.metrics import MetricResult

LAYER = "post_open_pipeline"

# Trajectory pairs: prior surface (reach) → post-open surface (hunt).
# Gold lives in annotations/overrides.jsonl; fixtures are harvests of real runs.
PIPELINE_PAIRS: Tuple[Dict[str, str], ...] = (
    {
        "name": "open_pallavi_then_hunt",
        "prior_id": "open_source/frame_0056",
        "after_id": "find_link/frame_0059",
        "expect_open": "Pallavi",
        "expect_query": "zarooratwala",
    },
    {
        "name": "open_pallavi_then_hunt_next_frame",
        "prior_id": "open_source/frame_0056",
        "after_id": "find_link/frame_0060",
        "expect_open": "Pallavi",
        "expect_query": "zarooratwala",
    },
)

# Families that advance content hunt inside an already-open source surface.
_HUNT_FAMILIES = frozenset(
    {
        "locate_content",
        "select_content",
        "reveal_actions",
        "scroll_content",
        "scroll",  # recorded replies sometimes still emit scroll; brain should prefer locate
    }
)
_FORBIDDEN_POST_OPEN = frozenset(
    {
        "open_entity",
        "open_contact",
        "compose_search_query",  # sidebar search — abandons the open-chat hunt
        "open_search",
    }
)

# AX / OCR titles that are chrome, not an open conversation referent.
_SEARCH_CHROME_OPEN = re.compile(
    r"^(q\s+)?search\|?$|^cmd\+f|^type to search",
    re.IGNORECASE,
)


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def _rate(hits: float, total: float) -> Optional[float]:
    return None if total <= 0 else hits / total


def _is_search_chrome_open(text: Any) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if _SEARCH_CHROME_OPEN.match(raw):
        return True
    # Loose: starts with "Q " and contains Search — AX title latch.
    low = raw.lower()
    return low.startswith("q ") and "search" in low


@dataclass
class PieceCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class PieceScore:
    piece: str
    trajectory: str
    fixture_id: str
    checks: List[PieceCheck] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)

    @property
    def score(self) -> float:
        if not self.checks:
            return 0.0
        return round(sum(1 for c in self.checks if c.passed) / len(self.checks), 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "piece": self.piece,
            "trajectory": self.trajectory,
            "fixture_id": self.fixture_id,
            "score": self.score,
            "checks": [c.to_dict() for c in self.checks],
            "failures": [c.name for c in self.checks if not c.passed],
            **({"extras": self.extras} if self.extras else {}),
        }


def _fixtures_by_id(fixtures: Sequence[Fixture]) -> Dict[str, Fixture]:
    return {f.id: f for f in fixtures}


def _gold_open(fixture: Fixture, fallback: str = "") -> str:
    ann = fixture.annotation or {}
    return str(ann.get("open_conversation") or fallback or "").strip()


def _reading_open(reading: Dict[str, Any]) -> str:
    return str(
        (reading.get("world_model") or {}).get("open_conversation")
        or (reading.get("observed_state") or {}).get("open_conversation")
        or ""
    ).strip()


def _reading_surface(reading: Dict[str, Any]) -> str:
    return _norm(
        (reading.get("world_model") or {}).get("surface")
        or (reading.get("observed_state") or {}).get("surface")
    )


def _goal_from_fixture(fixture: Fixture):
    from plugin.agent.goal import Goal

    g = fixture.goal
    return Goal(
        kind="whatsapp_forward_message",
        app="WhatsApp",
        contact=str(g.get("source_conversation") or g.get("contact") or ""),
        link_query=str(g.get("source_query") or g.get("link_query") or ""),
        target_contact=str(g.get("destination") or g.get("target_contact") or ""),
        prompt=str(g.get("description") or ""),
    )


def _proposal_from_reading(reading: Dict[str, Any]):
    from plugin.agent.unified_cognition import UnifiedProposal

    return UnifiedProposal(
        world_model=dict(reading.get("world_model") or {}),
        observed_state=dict(reading.get("observed_state") or {}),
        next_action={},
        suggested_actions=[
            a for a in (reading.get("suggested_actions") or reading.get("next_actions") or []) if isinstance(a, dict)
        ],
        next_actions=[a for a in (reading.get("next_actions") or []) if isinstance(a, dict)],
        visible_objects=[o for o in (reading.get("visible_objects") or []) if isinstance(o, dict)],
        missing_evidence=list(reading.get("missing_evidence") or []),
        evidence_gaps=list(reading.get("evidence_gaps") or []),
        affordance_qc=dict(reading.get("affordance_qc") or {}),
        scene_summary=str(reading.get("scene_summary") or ""),
        confidence=float(reading.get("confidence") or 0.0),
        model=str(reading.get("model") or ""),
    )


# ---------------------------------------------------------------------------
# Piece A — Perception
# ---------------------------------------------------------------------------


def score_perception(
    after: Fixture,
    reading: Optional[Dict[str, Any]],
    *,
    trajectory: str,
    expect_open: str,
) -> PieceScore:
    """Multimodal reading after open_entity: conversation + open contact."""
    result = PieceScore(piece="A_perception", trajectory=trajectory, fixture_id=after.id)
    gold_surface = _norm((after.annotation or {}).get("surface")) or "conversation"
    if not reading:
        result.checks.append(PieceCheck("model_returned_a_reading", False, "no reading"))
        return result

    fusion = score_fusion_reading(after, reading)
    result.checks.append(
        PieceCheck(
            "fusion_surface_matches_gold",
            any(c.name == "surface_matches_gold" and c.passed for c in fusion.checks),
            f"gold={fusion.surface_gold!r} got={fusion.surface_got!r}",
        )
    )
    got_surface = _reading_surface(reading)
    result.checks.append(
        PieceCheck(
            "surface_is_conversation",
            got_surface == "conversation",
            f"got={got_surface!r} expect=conversation (gold={gold_surface!r})",
        )
    )
    got_open = _reading_open(reading)
    expect = expect_open or _gold_open(after)
    open_ok = bool(expect) and _norm(expect) in _norm(got_open)
    result.checks.append(
        PieceCheck(
            "open_conversation_matches_source",
            open_ok,
            f"expect~={expect!r} got={got_open!r}",
        )
    )
    result.checks.append(
        PieceCheck(
            "open_conversation_not_search_chrome",
            not _is_search_chrome_open(got_open),
            f"open={got_open!r}",
        )
    )
    # Content may be off-screen; perception should admit the gap, not invent it.
    state = reading.get("observed_state") if isinstance(reading.get("observed_state"), dict) else {}
    missing = reading.get("missing_evidence") or []
    gaps = reading.get("evidence_gaps") or []
    query = _norm(after.goal.get("source_query") or after.goal.get("link_query"))
    admits_gap = (
        state.get("target_object_visible") is False
        or bool(missing)
        or bool(gaps)
        or (query and query not in _norm(reading.get("scene_summary") or ""))
    )
    result.checks.append(
        PieceCheck(
            "admits_content_not_yet_visible_or_names_gap",
            admits_gap,
            f"target_visible={state.get('target_object_visible')} missing={len(missing)} gaps={len(gaps)}",
        )
    )
    result.extras = {
        "surface": got_surface,
        "open_conversation": got_open,
        "model": str(reading.get("model") or ""),
        "latency_s": reading.get("latency_s"),
    }
    return result


# ---------------------------------------------------------------------------
# Piece B — Critic
# ---------------------------------------------------------------------------


def score_critic(
    prior: Fixture,
    after: Fixture,
    reading: Dict[str, Any],
    *,
    trajectory: str,
    expect_open: str,
    last_action: str = "open_entity",
) -> PieceScore:
    """Critic accepts conversation + contact after open_entity."""
    from plugin.agent.world_critic import critique_world_proposal
    from plugin.experiments.world_critic_eval import score_accepted_representation

    result = PieceScore(piece="B_critic", trajectory=trajectory, fixture_id=after.id)
    prior_doc = dict(prior.document or prior.prior_document or {})
    if not prior_doc.get("surface"):
        prior_doc["surface"] = _norm((prior.annotation or {}).get("surface")) or "chat_list"
    proposal = dict(reading.get("world_model") or {})
    if not proposal.get("surface"):
        proposal["surface"] = _reading_surface(reading)
    if not proposal.get("open_conversation"):
        proposal["open_conversation"] = _reading_open(reading)

    expect = expect_open or _gold_open(after)
    verdict = critique_world_proposal(
        prior_doc,
        proposal,
        last_action=last_action,
    )
    accepted = dict(verdict.accepted_document or {})
    checks = score_accepted_representation(
        prior=prior_doc,
        proposal=proposal,
        accepted=accepted,
        verdict=verdict,
        expect_surface="conversation",
        expect_open=expect,
        # Conversation does not set the picker sidebar-motor gate; do not require it.
        expect_forbid_sidebar=None,
    )
    for c in checks:
        result.checks.append(PieceCheck(c.name, c.passed, c.detail))

    accepted_open = str(accepted.get("open_conversation") or "").strip()
    result.checks.append(
        PieceCheck(
            "accepted_open_not_search_chrome",
            not _is_search_chrome_open(accepted_open),
            f"accepted_open={accepted_open!r}",
        )
    )
    result.checks.append(
        PieceCheck(
            "accepted_surface_conversation",
            _norm(accepted.get("surface")) == "conversation",
            f"surface={accepted.get('surface')!r}",
        )
    )
    result.extras = {
        "accepted_surface": accepted.get("surface"),
        "accepted_open": accepted_open,
        "decisions": [
            {
                "field": getattr(d, "field", ""),
                "verdict": getattr(d, "verdict", ""),
                "reason": str(getattr(d, "reason", ""))[:120],
            }
            for d in (verdict.decisions or [])[:8]
        ],
    }
    return result


# ---------------------------------------------------------------------------
# Piece C — Brain
# ---------------------------------------------------------------------------


def score_brain(
    after: Fixture,
    accepted_world: Dict[str, Any],
    reading: Dict[str, Any],
    *,
    trajectory: str,
    expect_query: str = "",
) -> PieceScore:
    """Brain over critic-accepted world: hunt content, do not re-open / sidebar-search."""
    from plugin.agent.brain import choose_next_capability

    result = PieceScore(piece="C_brain", trajectory=trajectory, fixture_id=after.id)
    # Deterministic: heuristic chooser only (no live decision LLM in offline/CI).
    prev_llm = os.environ.get("HERMES_DECISION_LLM")
    os.environ["HERMES_DECISION_LLM"] = "0"
    try:
        proposal = _proposal_from_reading(reading)
        proposal.world_model = dict(accepted_world)
        # Ensure surface/open from critic win over a stale packet prior.
        proposal.observed_state = {
            **dict(proposal.observed_state or {}),
            "surface": accepted_world.get("surface"),
            "open_conversation": accepted_world.get("open_conversation"),
            "target_object_visible": False,
        }
        goal = _goal_from_fixture(after)
        # Minimal features so phase derivation sees conversation open.
        class _Features:
            conversation_open = True
            extras: Dict[str, Any] = {
                "open_conversation": str(accepted_world.get("open_conversation") or ""),
                "wa_screen": "conversation",
            }

        features = _Features()
        class _State:
            unified_world_document = dict(accepted_world)
            search_attempt_log: List[Any] = []
            last_plan_step = None

        state = _State()
        # Drop goal-matched objects so barren-Forward does not force observe
        # before content is located (hunt_content phase).
        cleaned_objects = []
        for obj in accepted_world.get("objects") or []:
            if not isinstance(obj, dict):
                continue
            o = dict(obj)
            # Keep geometry; clear false-positive matches_goal from list rows.
            if _norm(o.get("kind")) in {"chat_row", "contact"}:
                o["matches_goal"] = False
            cleaned_objects.append(o)
        state.unified_world_document["objects"] = cleaned_objects
        proposal.world_model["objects"] = cleaned_objects

        trace = choose_next_capability(proposal, goal, features=features, execution_state=state)
        family = _norm((proposal.next_action or {}).get("family"))
        text = str((proposal.next_action or {}).get("text") or "")
    finally:
        if prev_llm is None:
            os.environ.pop("HERMES_DECISION_LLM", None)
        else:
            os.environ["HERMES_DECISION_LLM"] = prev_llm

    result.checks.append(
        PieceCheck(
            "brain_emitted_a_capability",
            bool(family),
            f"family={family!r} trace_keys={list((trace or {}).keys())[:6]}",
        )
    )
    # Preferred: locate_content. Accept select/reveal only if somehow content-ready.
    prefer_locate = family == "locate_content"
    ok_hunt = family in _HUNT_FAMILIES or prefer_locate
    result.checks.append(
        PieceCheck(
            "brain_hunts_in_open_surface",
            ok_hunt,
            f"family={family!r} accept={sorted(_HUNT_FAMILIES)}",
        )
    )
    result.checks.append(
        PieceCheck(
            "brain_prefers_locate_content",
            prefer_locate,
            f"family={family!r} (design: source open + query pending → locate_content)",
        )
    )
    result.checks.append(
        PieceCheck(
            "brain_does_not_reopen_or_sidebar_search",
            family not in _FORBIDDEN_POST_OPEN,
            f"family={family!r} forbidden={sorted(_FORBIDDEN_POST_OPEN)}",
        )
    )
    result.checks.append(
        PieceCheck(
            "brain_does_not_stall_on_observe",
            family != "observe",
            f"family={family!r} — observe is reperceive, not the hunt move",
        )
    )
    query = expect_query or str(after.goal.get("source_query") or "")
    if prefer_locate and query:
        result.checks.append(
            PieceCheck(
                "locate_carries_goal_query",
                _norm(query) in _norm(text) or not text,
                # empty text ok if runtime authors from goal; non-empty must match
                f"query={query!r} text={text!r}",
            )
        )
    result.extras = {
        "family": family,
        "text": text,
        "phase": (trace or {}).get("phase"),
        "realization": (trace or {}).get("realization"),
    }
    return result


# ---------------------------------------------------------------------------
# Piece D — AX search-chrome trap (synthetic defect from live 111555)
# ---------------------------------------------------------------------------


def score_ax_chrome_trap(
    *,
    trajectory: str = "ax_search_chrome_trap",
    expect_open: str = "Pallavi",
) -> PieceScore:
    """AX reports search chrome as open title; critic must not adopt it."""
    from plugin.agent.world_critic import critique_world_proposal

    result = PieceScore(piece="D_ax_chrome_trap", trajectory=trajectory, fixture_id="synthetic/ax_q_search")
    prior = {
        "surface": "chat_list",
        "open_conversation": "",
        "objects": [
            {
                "id": "row",
                "kind": "chat_row",
                "text": expect_open,
                "matches_goal": True,
                "point": [190, 175],
            }
        ],
    }
    # Multimodal proposal is correct; AX-shaped noise tries to latch open title.
    proposal = {
        "surface": "conversation",
        "open_conversation": expect_open,
        "objects": [
            {
                "id": "header",
                "kind": "chat_header",
                "text": expect_open,
                "matches_goal": True,
                "point": [600, 40],
            },
            {
                "id": "msg",
                "kind": "message",
                "text": "recent message not the target",
                "matches_goal": False,
                "point": [600, 400],
            },
        ],
        "focused_field_role": "none",
    }
    # Contaminated merge path: proposal wrongly carries AX search chrome.
    contaminated = dict(proposal)
    contaminated["open_conversation"] = "Q Search|"

    verdict_good = critique_world_proposal(prior, proposal, last_action="open_entity")
    good_open = str((verdict_good.accepted_document or {}).get("open_conversation") or "")
    result.checks.append(
        PieceCheck(
            "clean_proposal_keeps_contact_open",
            _norm(expect_open) in _norm(good_open) and not _is_search_chrome_open(good_open),
            f"accepted_open={good_open!r}",
        )
    )

    verdict_bad = critique_world_proposal(prior, contaminated, last_action="open_entity")
    bad_open = str((verdict_bad.accepted_document or {}).get("open_conversation") or "")
    # Design intent: search chrome must not become the open conversation referent.
    # If this fails, the critic is the layer to fix — not a string blacklist in OCR.
    result.checks.append(
        PieceCheck(
            "contaminated_ax_title_not_accepted_as_open",
            not _is_search_chrome_open(bad_open),
            f"accepted_open={bad_open!r} (AX trap input was 'Q Search|')",
        )
    )
    result.checks.append(
        PieceCheck(
            "contaminated_still_conversation_surface",
            _norm((verdict_bad.accepted_document or {}).get("surface")) == "conversation",
            f"surface={(verdict_bad.accepted_document or {}).get('surface')!r}",
        )
    )
    result.extras = {"clean_open": good_open, "contaminated_accepted_open": bad_open}
    return result


# ---------------------------------------------------------------------------
# Trajectory runner
# ---------------------------------------------------------------------------


def _reading_for(
    fixture: Fixture,
    *,
    live: bool,
    record_dir: Path,
    provider: str,
    model: str,
    timeout_s: float,
) -> Tuple[Optional[Dict[str, Any]], str]:
    if live:
        if not resolve_screenshot(fixture, record_dir):
            return None, f"screenshot missing under {record_dir}"
        reading, _latency, err = replay_on_model(
            fixture,
            record_dir=record_dir,
            provider=provider,
            model=model,
            timeout_s=timeout_s,
        )
        if err and reading is None:
            return None, err
        return reading, ""
    if not fixture.response:
        return None, "no recorded response"
    return _proposal_from_response(fixture.response), ""


def run_trajectory(
    prior: Fixture,
    after: Fixture,
    *,
    name: str,
    expect_open: str,
    expect_query: str,
    live: bool = False,
    record_dir: Path = Path(DEFAULT_RECORD_DIR),
    provider: str = "ollama-cloud",
    model: str = "qwen3.5:397b",
    timeout_s: float = 180.0,
) -> Dict[str, Any]:
    reading, err = _reading_for(
        after,
        live=live,
        record_dir=record_dir,
        provider=provider,
        model=model,
        timeout_s=timeout_s,
    )
    pieces: List[PieceScore] = []
    perc = score_perception(after, reading, trajectory=name, expect_open=expect_open)
    if err:
        perc.checks.insert(0, PieceCheck("reading_available", False, err))
    pieces.append(perc)

    if reading:
        crit = score_critic(
            prior,
            after,
            reading,
            trajectory=name,
            expect_open=expect_open,
        )
        pieces.append(crit)
        from plugin.agent.world_critic import critique_world_proposal

        prior_doc = dict(prior.document or prior.prior_document or {})
        if not prior_doc.get("surface"):
            prior_doc["surface"] = "chat_list"
        proposal = dict(reading.get("world_model") or {})
        if not proposal.get("surface"):
            proposal["surface"] = _reading_surface(reading)
        if not proposal.get("open_conversation"):
            proposal["open_conversation"] = _reading_open(reading)
        verdict = critique_world_proposal(prior_doc, proposal, last_action="open_entity")
        accepted_world = dict(verdict.accepted_document or proposal)
        brain = score_brain(
            after,
            accepted_world,
            reading,
            trajectory=name,
            expect_query=expect_query,
        )
        pieces.append(brain)
    else:
        pieces.append(
            PieceScore(
                piece="B_critic",
                trajectory=name,
                fixture_id=after.id,
                checks=[PieceCheck("skipped", False, "no reading")],
            )
        )
        pieces.append(
            PieceScore(
                piece="C_brain",
                trajectory=name,
                fixture_id=after.id,
                checks=[PieceCheck("skipped", False, "no reading")],
            )
        )

    return {
        "name": name,
        "prior_id": prior.id,
        "after_id": after.id,
        "live": live,
        "pieces": [p.to_dict() for p in pieces],
        "piece_scores": {p.piece: p.score for p in pieces},
        "mean_score": round(sum(p.score for p in pieces) / max(1, len(pieces)), 4),
        "failures": [
            f"{p.piece}:{c.name}"
            for p in pieces
            for c in p.checks
            if not c.passed
        ],
    }


def summarize_post_open_pipeline(
    fixtures: Optional[Sequence[Fixture]] = None,
    *,
    live: bool = False,
    record_dir: str = DEFAULT_RECORD_DIR,
    model_spec: str = "ollama-cloud/qwen3.5:397b",
    timeout_s: float = 180.0,
    limit: int = 0,
) -> Dict[str, Any]:
    """Run all pipeline pairs + the synthetic AX chrome trap."""
    if fixtures is None:
        fixtures = annotate(load_fixtures(DEFAULT_CORPUS_DIR), overrides=load_overrides())
    else:
        fixtures = list(fixtures)
    by_id = _fixtures_by_id(fixtures)
    if "/" in model_spec:
        provider, model = model_spec.split("/", 1)
    else:
        provider, model = "ollama-cloud", model_spec

    trajectories: List[Dict[str, Any]] = []
    pairs = list(PIPELINE_PAIRS)
    if limit:
        pairs = pairs[: max(0, int(limit))]
    for pair in pairs:
        prior = by_id.get(pair["prior_id"])
        after = by_id.get(pair["after_id"])
        if prior is None or after is None:
            trajectories.append(
                {
                    "name": pair["name"],
                    "error": f"missing fixtures prior={pair['prior_id']} after={pair['after_id']}",
                    "mean_score": 0.0,
                    "failures": ["fixtures_missing"],
                }
            )
            continue
        trajectories.append(
            run_trajectory(
                prior,
                after,
                name=pair["name"],
                expect_open=pair["expect_open"],
                expect_query=pair["expect_query"],
                live=live,
                record_dir=Path(record_dir),
                provider=provider.strip(),
                model=model.strip(),
                timeout_s=timeout_s,
            )
        )

    ax_trap = score_ax_chrome_trap()
    trap_dict = ax_trap.to_dict()

    piece_means: Dict[str, List[float]] = {}
    for traj in trajectories:
        for piece_name, score in (traj.get("piece_scores") or {}).items():
            piece_means.setdefault(piece_name, []).append(float(score))
    piece_means.setdefault("D_ax_chrome_trap", []).append(ax_trap.score)

    metrics = [
        MetricResult(
            name="perception_post_open_surface",
            layer=LAYER,
            value=_rate(
                sum(1 for t in trajectories if (t.get("piece_scores") or {}).get("A_perception", 0) >= 0.8),
                len([t for t in trajectories if "piece_scores" in t]),
            ),
            scored=len([t for t in trajectories if "piece_scores" in t]),
            skipped=0,
            question="After open_entity, does perception name conversation + open contact?",
            examples=[f for t in trajectories for f in (t.get("failures") or []) if f.startswith("A_")][:8],
        ),
        MetricResult(
            name="critic_accepts_post_open",
            layer=LAYER,
            value=_rate(
                sum(1 for t in trajectories if (t.get("piece_scores") or {}).get("B_critic", 0) >= 0.8),
                len([t for t in trajectories if "piece_scores" in t]),
            ),
            scored=len([t for t in trajectories if "piece_scores" in t]),
            skipped=0,
            question="Does the critic accept conversation and keep the source open?",
            examples=[f for t in trajectories for f in (t.get("failures") or []) if f.startswith("B_")][:8],
        ),
        MetricResult(
            name="brain_locate_after_open",
            layer=LAYER,
            value=_rate(
                sum(1 for t in trajectories if (t.get("piece_scores") or {}).get("C_brain", 0) >= 0.8),
                len([t for t in trajectories if "piece_scores" in t]),
            ),
            scored=len([t for t in trajectories if "piece_scores" in t]),
            skipped=0,
            question="Does the brain choose locate_content (hunt) on the open source?",
            examples=[f for t in trajectories for f in (t.get("failures") or []) if f.startswith("C_")][:8],
        ),
        MetricResult(
            name="ax_search_chrome_not_open_title",
            layer=LAYER,
            value=ax_trap.score,
            scored=len(ax_trap.checks),
            skipped=0,
            question="When AX latches search chrome as open title, does the critic refuse it?",
            examples=ax_trap.to_dict().get("failures") or [],
        ),
    ]

    mean = None
    scored_traj = [t for t in trajectories if "mean_score" in t]
    if scored_traj:
        mean = round(
            (sum(float(t["mean_score"]) for t in scored_traj) + ax_trap.score)
            / (len(scored_traj) + 1),
            4,
        )

    return {
        "layer": LAYER,
        "live": live,
        "model": model_spec if live else "recorded",
        "trajectories": trajectories,
        "ax_chrome_trap": trap_dict,
        "piece_means": {
            k: round(sum(v) / len(v), 4) if v else None for k, v in piece_means.items()
        },
        "mean_pipeline_score": mean,
        "metrics": [m.to_dict() for m in metrics],
        "fixtures_scored": len(scored_traj),
    }


def render_report(report: Dict[str, Any]) -> str:
    lines = [
        f"post_open_pipeline — mean={report.get('mean_pipeline_score')}  "
        f"trajectories={report.get('fixtures_scored')}  "
        f"mode={'live:' + str(report.get('model')) if report.get('live') else 'offline/recorded'}",
    ]
    means = report.get("piece_means") or {}
    if means:
        lines.append("  piece means: " + "  ".join(f"{k}={v}" for k, v in means.items()))
    for metric in report.get("metrics") or []:
        value = metric.get("value")
        rendered = f"{value:.0%}" if isinstance(value, float) else "n/a"
        lines.append(
            f"  {str(metric.get('name') or ''):<36} {rendered:>8}  "
            f"scored={metric.get('scored', 0)}"
        )
        for ex in (metric.get("examples") or [])[:3]:
            lines.append(f"      fail {ex}")
    for traj in report.get("trajectories") or []:
        fails = traj.get("failures") or []
        mark = "OK" if not fails else "FAIL"
        lines.append(
            f"  [{mark}] {traj.get('name')}  "
            f"scores={traj.get('piece_scores')}  "
            f"failures={fails[:6]}"
        )
    trap = report.get("ax_chrome_trap") or {}
    lines.append(
        f"  [{'OK' if not trap.get('failures') else 'FAIL'}] "
        f"D_ax_chrome_trap score={trap.get('score')} failures={trap.get('failures')}"
    )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Piecewise post-open pipeline eval")
    parser.add_argument("--corpus", default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--live", action="store_true", help="re-ask a real perceptor on screenshots")
    parser.add_argument("--record-dir", default=DEFAULT_RECORD_DIR)
    parser.add_argument("--model", default="ollama-cloud/qwen3.5:397b")
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument("--limit", type=int, default=0, help="limit trajectory pairs")
    parser.add_argument("--json", default="", help="write full report JSON")
    args = parser.parse_args(argv)

    fixtures = annotate(load_fixtures(args.corpus), overrides=load_overrides())
    report = summarize_post_open_pipeline(
        fixtures,
        live=args.live,
        record_dir=args.record_dir,
        model_spec=args.model,
        timeout_s=args.timeout_s,
        limit=args.limit,
    )
    print(render_report(report))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nreport written to {args.json}")
    # Non-zero when brain or AX trap fails hard — those are the live stall layers.
    piece_means = report.get("piece_means") or {}
    brain = piece_means.get("C_brain")
    trap = piece_means.get("D_ax_chrome_trap")
    bad = (isinstance(brain, float) and brain < 0.5) or (isinstance(trap, float) and trap < 1.0)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
