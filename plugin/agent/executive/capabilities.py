"""Capability descriptors and a registry with hierarchical retrieval.

The hardcoded catalog (``plugin.agent.capabilities.catalog``) says *what* verbs
exist and *how* they map to motor primitives. It says nothing about what a
capability costs, how long it takes, how often it works, what has to be true
before it can run, or what it changes in the world. Consultation therefore had
to send the model the whole list every time and hope it chose well.

A ``CapabilityDescriptor`` adds that operational metadata, and the
``CapabilityRegistry`` uses it to retrieve capabilities hierarchically: first
the ones whose preconditions the current situation satisfies, then ranked by
value for the meta-action at hand. The executive can hand the reasoning model a
short, relevant shortlist instead of the full catalog, and can reason about
cost, reversibility and side effects itself.

This wraps the existing catalog rather than replacing its data, so no
construction site of the frozen ``CapabilitySpec`` has to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from plugin.agent.capabilities.base import CapabilitySpec, Substrate
from plugin.agent.capabilities.catalog import all_specs


class Cost(str):
    pass


COST_RANK = {"low": 1, "medium": 2, "high": 3}


# Capability families group verbs by what they are *for*, so retrieval can do
# progressive disclosure ("N of M relevant") rather than dumping the catalog.
CAPABILITY_FAMILIES: Dict[str, str] = {
    "compose_search_query": "search",
    "locate_content": "search",
    "resolve_entity": "disambiguation",
    "open_entity": "navigation",
    "reveal_actions": "navigation",
    "dismiss_transient": "navigation",
    "select_content": "selection",
    "invoke_affordance": "action",
    "commit_irreversible": "action",
}


@dataclass(frozen=True)
class CapabilityDescriptor:
    """A capability plus what it costs, needs, changes, and consumes/produces."""

    spec: CapabilitySpec
    cost: str = "low"  # low | medium | high  (steps / user attention)
    latency: str = "low"  # low | medium | high  (wall-clock)
    reliability: float = 0.7  # 0..1, historical success on this verb
    # Facts that must hold before the capability can run. Matched against the
    # situation's declared facts (surface, substrate availability, bindings).
    preconditions: Tuple[str, ...] = ()
    # What the capability changes. "none" for pure reads; "navigation" for a
    # reversible surface change; "irreversible" for send/delete/confirm.
    side_effects: Tuple[str, ...] = ("none",)
    # What the capability consumes and produces, so the executive can reason
    # about wiring one capability's output into another's input.
    inputs: Tuple[str, ...] = ()
    outputs: Tuple[str, ...] = ()
    # "verb" for a catalog primitive, "skill" / "bounded_agent" for a capability
    # that itself runs a loop and returns a bounded result.
    kind: str = "verb"

    @property
    def family(self) -> str:
        return CAPABILITY_FAMILIES.get(self.spec.name, "action")

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def verb(self) -> str:
        return self.spec.verb

    @property
    def reversible(self) -> bool:
        return self.spec.reversible

    @property
    def substrate(self) -> Substrate:
        return self.spec.substrate

    @property
    def is_irreversible(self) -> bool:
        return (not self.spec.reversible) or ("irreversible" in self.side_effects)

    def preconditions_met(self, facts: Iterable[str]) -> bool:
        have = {str(f).strip().lower() for f in facts if str(f).strip()}
        return all(pre in have for pre in self.preconditions)

    def value(self) -> float:
        """Cheap, reliable, reversible capabilities are worth more."""
        cost_penalty = COST_RANK.get(self.cost, 1)
        base = self.reliability / float(cost_penalty)
        if self.is_irreversible:
            base *= 0.6  # never volunteer an irreversible move on value alone
        return round(base, 4)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "verb": self.verb,
            "kind": self.kind,
            "family": self.family,
            "cost": self.cost,
            "latency": self.latency,
            "reliability": round(self.reliability, 3),
            "reversible": self.reversible,
            "preconditions": list(self.preconditions),
            "side_effects": list(self.side_effects),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "value": self.value(),
        }


# Operational metadata for the built-in catalog verbs. Reliability seeds are
# conservative priors; a live registry can update them from capability memory.
_OPERATIONAL: Dict[str, Dict[str, object]] = {
    "compose_search_query": dict(
        cost="low", latency="low", reliability=0.85,
        preconditions=("task_evidence",), side_effects=("none",),
        inputs=("goal_query", "prior_attempts"), outputs=("search_query",),
    ),
    "locate_content": dict(
        cost="low", latency="medium", reliability=0.6,
        preconditions=("searchable_surface",), side_effects=("none",),
        inputs=("query", "open_surface"), outputs=("content_visible",),
    ),
    "open_entity": dict(
        cost="medium", latency="medium", reliability=0.7,
        preconditions=("addressable_entity",), side_effects=("navigation",),
        inputs=("entity_label", "point"), outputs=("open_conversation", "surface"),
    ),
    "resolve_entity": dict(
        cost="low", latency="low", reliability=0.65,
        preconditions=("candidate_set",), side_effects=("none",),
        inputs=("referent", "candidate_set"), outputs=("chosen_entity",),
    ),
    "select_content": dict(
        cost="low", latency="low", reliability=0.7,
        preconditions=("addressable_entity",), side_effects=("focus",),
        inputs=("entity_label",), outputs=("selection",),
    ),
    "reveal_actions": dict(
        cost="low", latency="low", reliability=0.8,
        preconditions=("addressable_entity",), side_effects=("navigation",),
        inputs=("entity_label",), outputs=("affordance_set",),
    ),
    "invoke_affordance": dict(
        cost="medium", latency="medium", reliability=0.65,
        preconditions=("affordance_set",), side_effects=("navigation",),
        inputs=("affordance_label",), outputs=("surface",),
    ),
    "dismiss_transient": dict(
        cost="low", latency="low", reliability=0.9,
        preconditions=("transient_chrome",), side_effects=("navigation",),
        inputs=(), outputs=("surface",),
    ),
    "commit_irreversible": dict(
        cost="high", latency="low", reliability=0.9,
        preconditions=("gated_target",), side_effects=("irreversible",),
        inputs=("gated_target",), outputs=("committed",),
    ),
}


def _descriptor_for(spec: CapabilitySpec) -> CapabilityDescriptor:
    meta = _OPERATIONAL.get(spec.name, {})
    return CapabilityDescriptor(
        spec=spec,
        cost=str(meta.get("cost", "low")),
        latency=str(meta.get("latency", "low")),
        reliability=float(meta.get("reliability", 0.7)),
        preconditions=tuple(meta.get("preconditions", ())),
        side_effects=tuple(meta.get("side_effects", ("none",))),
        inputs=tuple(meta.get("inputs", ())),
        outputs=tuple(meta.get("outputs", ())),
        kind=str(meta.get("kind", "verb")),
    )


@dataclass
class CapabilityRegistry:
    """The retrieval front-end over the catalog."""

    descriptors: Dict[str, CapabilityDescriptor] = field(default_factory=dict)

    @classmethod
    def from_catalog(cls, specs: Optional[Sequence[CapabilitySpec]] = None) -> "CapabilityRegistry":
        specs = list(specs) if specs is not None else list(all_specs())
        return cls(descriptors={s.name: _descriptor_for(s) for s in specs})

    def get(self, name: str) -> Optional[CapabilityDescriptor]:
        return self.descriptors.get(str(name or "").strip().lower())

    def observe_reliability(self, name: str, success: bool) -> None:
        """Nudge a verb's reliability toward observed outcomes (EMA)."""
        desc = self.get(name)
        if desc is None:
            return
        target = 1.0 if success else 0.0
        updated = 0.85 * desc.reliability + 0.15 * target
        self.descriptors[desc.name] = CapabilityDescriptor(
            spec=desc.spec,
            cost=desc.cost,
            latency=desc.latency,
            reliability=round(updated, 4),
            preconditions=desc.preconditions,
            side_effects=desc.side_effects,
            inputs=desc.inputs,
            outputs=desc.outputs,
            kind=desc.kind,
        )

    def register(self, descriptor: CapabilityDescriptor) -> None:
        """Add a capability — including a skill / bounded sub-agent — by descriptor.

        Skills are capabilities like any other: they advertise cost, reliability,
        preconditions and I/O, and the executive retrieves them the same way it
        retrieves a primitive verb.
        """
        self.descriptors[descriptor.name] = descriptor

    def families(self) -> Dict[str, List[str]]:
        """Capability names grouped by family, for progressive disclosure."""
        out: Dict[str, List[str]] = {}
        for desc in self.descriptors.values():
            out.setdefault(desc.family, []).append(desc.name)
        for names in out.values():
            names.sort()
        return out

    def retrieve(
        self,
        *,
        facts: Iterable[str] = (),
        substrate: Optional[str] = None,
        reversible_only: bool = False,
        include_irreversible: bool = True,
        limit: int = 4,
    ) -> List[CapabilityDescriptor]:
        """Hierarchical retrieval: filter by fit, then rank by value.

        Level 1 keeps only capabilities whose preconditions the situation
        satisfies (and honours the reversibility constraint). Level 2 ranks the
        survivors by their value score so the model sees the cheapest reliable
        options first.
        """
        facts = list(facts)
        want_substrate = str(substrate or "").strip().lower()

        candidates: List[CapabilityDescriptor] = []
        for desc in self.descriptors.values():
            if reversible_only and desc.is_irreversible:
                continue
            if not include_irreversible and desc.is_irreversible:
                continue
            if want_substrate and desc.substrate.value != want_substrate:
                continue
            if facts and desc.preconditions and not desc.preconditions_met(facts):
                continue
            candidates.append(desc)

        candidates.sort(key=lambda d: d.value(), reverse=True)
        return candidates[: max(1, limit)]

    def shortlist_for(
        self,
        *,
        meta_action: str = "act",
        facts: Iterable[str] = (),
        substrate: Optional[str] = None,
        limit: int = 4,
    ) -> List[CapabilityDescriptor]:
        """A meta-action-aware shortlist for a consultation.

        PROBE/PERCEIVE want cheap reversible reveals; ACT allows the committing
        moves; anything else gets the reversible shortlist by default.
        """
        action = str(meta_action or "act").strip().lower()
        if action in {"probe", "perceive", "verify", "think", "backtrack"}:
            return self.retrieve(
                facts=facts, substrate=substrate, reversible_only=True, limit=limit
            )
        return self.retrieve(facts=facts, substrate=substrate, limit=limit)

    def disclosure(
        self,
        *,
        meta_action: str = "act",
        facts: Iterable[str] = (),
        substrate: Optional[str] = None,
        limit: int = 4,
    ) -> Dict[str, object]:
        """A progressive-disclosure view: the relevant shortlist, plus the map.

        Instead of handing a consultation the whole catalog, expose only the
        top ``limit`` relevant capabilities, say how many of the total that is,
        and offer the family taxonomy so the model can request a family it wants
        expanded rather than seeing everything up front.
        """
        shortlist = self.shortlist_for(
            meta_action=meta_action, facts=facts, substrate=substrate, limit=limit
        )
        return {
            "relevant": [d.to_dict() for d in shortlist],
            "relevant_count": len(shortlist),
            "installed_count": len(self.descriptors),
            "families": {fam: len(names) for fam, names in self.families().items()},
        }

    def expand_family(self, family: str) -> List[CapabilityDescriptor]:
        """The capabilities in a family, for a model's expansion request."""
        want = str(family or "").strip().lower()
        out = [d for d in self.descriptors.values() if d.family == want]
        out.sort(key=lambda d: d.value(), reverse=True)
        return out

    def to_dict(self) -> Dict[str, object]:
        return {name: desc.to_dict() for name, desc in self.descriptors.items()}


_DEFAULT_REGISTRY: Optional[CapabilityRegistry] = None


def default_registry() -> CapabilityRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = CapabilityRegistry.from_catalog()
    return _DEFAULT_REGISTRY
