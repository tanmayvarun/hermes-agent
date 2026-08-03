"""Ground truth for the corpus, kept independent of the thing being scored.

The temptation with recorded frames is to label them from the reply that was
recorded alongside. That produces an eval which agrees with itself: a model
that confidently misread the screen would be scored against its own misreading
and come out perfect.

So every derived label here comes from one of three sources the model did not
produce:

  shadow      AX-derived predicates captured during the run but never sent
  outcome     what the *next* frame shows the last action actually did
  contract    the task's own composition rules, written down here

Anything none of those can settle is left unlabelled. A metric skips unlabelled
fields and reports coverage, which is more useful than a confident score over
labels nobody checked. Human labels go in ``overrides.jsonl`` keyed by fixture
id and always win.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from plugin.evals.corpus import Fixture, model_surface, shadow_surface

SOURCE_SHADOW = "shadow"
# The shadow screen label is computed over the *fused* world, which on an app
# with no accessible content is populated from the model's own object
# inventory. So it is only partly independent of the reply, and a metric
# scored against it is measuring self-consistency as much as correctness.
# Labelled distinctly so a report can say so, and superseded by any manual
# label for the same fixture.
SOURCE_SHADOW_FUSED = "shadow_fused"
SOURCE_OUTCOME = "outcome"
SOURCE_CONTRACT = "contract"
SOURCE_MANUAL = "manual"

OVERRIDES_FILE = "plugin/evals/annotations/overrides.jsonl"

# --- the task contract -------------------------------------------------------
#
# What each surface is *for* during a forward, written independently of any
# model output. These are the acceptable / unacceptable action sets the ranking
# metrics score against, and the critical-CTA sets the frontier is measured on.
#
# utility feeds NDCG-style scoring: 3 is the move that advances the task, 2 an
# acceptable alternative, 1 a defensible probe, 0 wasted, negative dangerous.

SURFACE_CONTRACT: Dict[str, Dict[str, Any]] = {
    "chat_list": {
        "critical": ("compose_search_query", "type_query", "open_entity", "resolve_entity"),
        "acceptable": {
            "compose_search_query": 3,
            "type_query": 3,
            "resolve_entity": 3,
            "open_entity": 2,
            "scroll": 1,
            "observe": 0,
        },
        "forbidden": ("commit_irreversible", "invoke_affordance", "locate_content"),
        "latent": (),
    },
    "search": {
        "critical": ("resolve_entity", "open_entity", "type_query", "compose_search_query"),
        "acceptable": {
            "resolve_entity": 3,
            "open_entity": 3,
            "compose_search_query": 2,
            "type_query": 2,
            "scroll": 1,
            "observe": 0,
        },
        "forbidden": ("commit_irreversible", "invoke_affordance"),
        "latent": (),
    },
    "conversation": {
        "critical": ("locate_content", "select_content", "reveal_actions"),
        "acceptable": {
            "locate_content": 3,
            "select_content": 3,
            "reveal_actions": 3,
            "scroll": 2,
            "hover": 1,
            "observe": 0,
        },
        # Sidebar search from an open source conversation is the drift class
        # that abandoned the hunt and re-opened the wrong chat.
        "forbidden": ("compose_search_query", "commit_irreversible"),
        "latent": ("Forward", "Reply", "Copy"),
    },
    "context_menu": {
        "critical": ("invoke_affordance",),
        "acceptable": {"invoke_affordance": 3, "dismiss_transient": 1, "observe": 0},
        "forbidden": ("compose_search_query", "type_query", "locate_content", "commit_irreversible"),
        "latent": (),
    },
    "forward_picker": {
        "critical": ("resolve_entity", "type_query"),
        "acceptable": {
            "resolve_entity": 3,
            "open_entity": 2,
            "type_query": 2,
            "commit_irreversible": 1,
            "observe": 0,
        },
        "forbidden": ("compose_search_query", "locate_content", "reveal_actions"),
        "latent": ("Send",),
    },
    "dialog": {
        "critical": (),
        "acceptable": {"commit_irreversible": 3, "dismiss_transient": 2, "observe": 0},
        "forbidden": ("compose_search_query", "locate_content"),
        "latent": (),
    },
    "blank": {
        "critical": (),
        "acceptable": {"observe": 2, "compose_search_query": 2, "dismiss_transient": 1},
        "forbidden": ("commit_irreversible",),
        "latent": (),
    },
}

# Labels that belong to the application shell, never to the task. Used both as
# the pollution ground truth and as forbidden action targets.
CHROME_ROLES = {"axapplication", "axwindow", "axmenubar", "axmenubaritem", "axtoolbar"}
# Matched as whole labels or leading words, never as bare prefixes: "Help"
# is a menu, "Helping Hands - IITR 2013" is a group chat, and a startswith
# test cannot tell them apart.
CHROME_LABELS = (
    "whatsapp",
    "apple",
    "file",
    "edit",
    "view",
    "window",
    "help",
    "services",
    "hide",
    "quit",
    "settings",
)
CHROME_NOTICES = ("end-to-end encrypted", "click to learn more")

# Motor verbs the model may name instead of a capability. Scoring the spelling
# rather than the intent would make the ranking metric a vocabulary check.
MOTOR_TO_FAMILY: Dict[str, str] = {
    "right_click": "reveal_actions",
    "context_click": "reveal_actions",
    "hover": "hover",
    "type": "type_query",
    "press_escape": "dismiss_transient",
    "dismiss": "dismiss_transient",
    "open_contact": "open_entity",
    "select_forward_target": "resolve_entity",
    "forward_message": "invoke_affordance",
}
# A bare click means whichever object the surface is there to act on.
CLICK_BY_SURFACE: Dict[str, str] = {
    "chat_list": "open_entity",
    "search": "open_entity",
    "conversation": "select_content",
    "context_menu": "invoke_affordance",
    "forward_picker": "resolve_entity",
    "dialog": "commit_irreversible",
}


def normalize_family(family: str, surface: str = "") -> str:
    """The capability a proposed action amounts to on this surface."""
    name = _norm(family).replace("-", "_")
    if name == "click":
        return CLICK_BY_SURFACE.get(_norm(surface), "open_entity")
    return MOTOR_TO_FAMILY.get(name, name)


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def is_chrome_node(node: Dict[str, Any]) -> bool:
    """Whether an AX node is application shell rather than task content."""
    role = _norm(node.get("role"))
    label = _norm(node.get("label"))
    bounds = node.get("bounds") or []
    if role in CHROME_ROLES:
        return True
    if any(label == term or label.startswith(term + " ") for term in CHROME_LABELS):
        return True
    if any(notice in label for notice in CHROME_NOTICES):
        return True
    try:
        if len(bounds) >= 4 and (float(bounds[2]) <= 0 or float(bounds[3]) <= 0):
            return True
    except (TypeError, ValueError):
        pass
    return False


def required_controls(surface: str, goal: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Controls that must survive sensing for the phase to be actionable.

    Weighted the way the spec asks: an extractor that returns 95% of nodes and
    drops the search field has failed, and a flat recall number would hide it.
    """
    source = str(goal.get("source_conversation") or "")
    query = str(goal.get("source_query") or "")
    destination = str(goal.get("destination") or "")
    if surface in {"chat_list", "search"}:
        return [
            {"kind": "search_input", "weight": 10, "why": "the query has to be typed somewhere"},
            {"kind": "conversation_row", "label": source, "weight": 10, "why": "the source chat must be openable"},
        ]
    if surface == "conversation":
        return [
            {"kind": "message", "label": query, "weight": 10, "why": "the message being forwarded"},
            {"kind": "timeline", "weight": 5, "why": "history has to be scrollable"},
        ]
    if surface == "context_menu":
        return [{"kind": "menu_item", "label": "Forward", "weight": 10, "why": "the affordance being invoked"}]
    if surface == "forward_picker":
        return [
            {"kind": "destination_row", "label": destination, "weight": 10, "why": "the recipient"},
            {"kind": "destination_filter", "weight": 5, "why": "narrowing the recipient list"},
        ]
    return []


def label_matches(node_label: str, wanted: str) -> bool:
    left, right = _norm(node_label), _norm(wanted)
    if not left or not right:
        return False
    return right in left or left in right


def _target_object(fixture: Fixture) -> Optional[Dict[str, Any]]:
    """The object the goal is about, identified without trusting the reply.

    The reply's own object inventory is under test, so a match there is only
    accepted when the AX evidence or the goal query independently names it.
    """
    query = _norm(fixture.goal.get("source_query"))
    if not query:
        return None
    for node in fixture.ax_evidence:
        if query in _norm(node.get("label")) or query in _norm(node.get("description")):
            return {"text": node.get("label"), "ax_id": node.get("id"), "evidence": "ax"}
    return None


def outcome_surface(next_fixture: Optional[Fixture]) -> str:
    """Where the next frame says the last action landed."""
    if next_fixture is None:
        return ""
    return shadow_surface(next_fixture) or ""


def derive_annotation(
    fixture: Fixture,
    *,
    next_fixture: Optional[Fixture] = None,
) -> Dict[str, Any]:
    """Label what the available evidence can settle, and say what it cannot."""
    sources: Dict[str, str] = {}
    annotation: Dict[str, Any] = {"unlabelled": []}

    ax_content = int(fixture.observation.get("ax_content_node_count") or 0)
    surface = ""
    ax_surface = shadow_surface(fixture)
    if ax_surface and ax_content > 0:
        surface = ax_surface
        sources["surface"] = SOURCE_SHADOW
    elif ax_surface:
        surface = ax_surface
        sources["surface"] = SOURCE_SHADOW_FUSED
    if surface:
        annotation["surface"] = surface
    else:
        annotation["unlabelled"].append("surface")

    contract = SURFACE_CONTRACT.get(surface or model_surface(fixture) or "blank", SURFACE_CONTRACT["blank"])
    annotation["critical_ctas"] = list(contract["critical"])
    annotation["acceptable_next_actions"] = dict(contract["acceptable"])
    annotation["forbidden_next_actions"] = list(contract["forbidden"])
    annotation["latent_affordances"] = list(contract["latent"])
    sources["actions"] = SOURCE_CONTRACT

    annotation["required_controls"] = required_controls(surface or model_surface(fixture), fixture.goal)
    annotation["chrome_node_ids"] = [
        node.get("id") for node in fixture.ax_evidence if is_chrome_node(node)
    ]
    sources["controls"] = SOURCE_CONTRACT

    target = _target_object(fixture)
    if target:
        annotation["target_object"] = target
        sources["target_object"] = SOURCE_SHADOW
    else:
        annotation["unlabelled"].append("target_object")

    landed = outcome_surface(next_fixture)
    if landed:
        annotation["observed_next_surface"] = landed
        sources["transition"] = SOURCE_OUTCOME
    else:
        annotation["unlabelled"].append("observed_next_surface")

    # Evidence the reply was entitled to rely on. The uncertainty metric needs
    # to know what the model could actually see before calling a claim
    # unsupported.
    annotation["evidence_available"] = {
        "screenshot": fixture.has_screenshot,
        "ax_content": ax_content > 0,
        "ax_nodes": int(fixture.observation.get("ax_node_count") or 0),
    }
    annotation["sources"] = sources
    return annotation


def load_overrides(path: str | Path = OVERRIDES_FILE) -> Dict[str, Dict[str, Any]]:
    """Human labels, one JSON object per line, keyed by fixture id."""
    file = Path(path)
    if not file.exists():
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for line in file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        fixture_id = str(raw.get("id") or "").strip()
        if fixture_id:
            out[fixture_id] = raw
    return out


def apply_override(annotation: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """A human label replaces the derived one and is marked as such."""
    if not override:
        return annotation
    merged = dict(annotation)
    unlabelled = set(merged.get("unlabelled") or [])
    sources = dict(merged.get("sources") or {})
    for key, value in override.items():
        if key in {"id", "note"}:
            continue
        merged[key] = value
        unlabelled.discard(key)
        sources[key] = SOURCE_MANUAL
    merged["unlabelled"] = sorted(unlabelled)
    merged["sources"] = sources
    if override.get("note"):
        merged["note"] = str(override["note"])
    return merged


def annotate(
    fixtures: Sequence[Fixture],
    *,
    overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Fixture]:
    """Attach ground truth to a corpus in run order, so outcomes can be read."""
    overrides = overrides if overrides is not None else load_overrides()
    ordered = sorted(fixtures, key=lambda f: int(f.source.get("frame") or 0))
    for index, fixture in enumerate(ordered):
        following = ordered[index + 1] if index + 1 < len(ordered) else None
        fixture.annotation = apply_override(
            derive_annotation(fixture, next_fixture=following), overrides.get(fixture.id)
        )
    return ordered


def annotation_coverage(fixtures: Iterable[Fixture]) -> Dict[str, Any]:
    """How much of the ground truth is actually settled, and by whom.

    Reported alongside every score. A 90% surface accuracy over 20% coverage
    is a different claim from the same number over the whole corpus.
    """
    total = 0
    labelled: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    for fixture in fixtures:
        total += 1
        annotation = fixture.annotation or {}
        unlabelled = set(annotation.get("unlabelled") or [])
        for field in ("surface", "target_object", "observed_next_surface"):
            if field not in unlabelled and annotation.get(field) not in (None, "", []):
                labelled[field] = labelled.get(field, 0) + 1
        for source in (annotation.get("sources") or {}).values():
            by_source[str(source)] = by_source.get(str(source), 0) + 1
    return {
        "fixtures": total,
        "labelled": labelled,
        "rates": {k: round(v / total, 3) for k, v in labelled.items()} if total else {},
        "label_sources": dict(sorted(by_source.items())),
    }
