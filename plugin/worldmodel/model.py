"""Layer 9 — WorldModel core. Zero LLM imports. Belief-aware ingest."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from plugin.perception.observation import Observation
from plugin.worldmodel.belief import Belief
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.entities.identity import IdentityTracker, MatchResult
from plugin.worldmodel.entities.normalize import (
    _clean_label,
    apply_cached_semantics,
    entities_from_observation,
)
from plugin.worldmodel.graph.navigation import NavigationGraph
from plugin.worldmodel.screens.detect import Screen, ScreenDetector
from plugin.worldmodel.transitions.transition import (
    Transition,
    TransitionStore,
    compute_entity_diff,
)

SOFT_DELETE_MISS_FRAMES = 3
EXISTS_DROP_CONFIDENCE = 0.25
_CHROME_ONLY_ROLES = {
    "axapplication",
    "axwindow",
    "axmenubar",
    "axmenubaritem",
    "axmenu",
    "axmenuitem",
}


@dataclass
class WorldPatch:
    retention: float
    screen_id: int
    screen_label: str
    new_entity_ids: List[int]
    matched_ids: List[int]
    transition: Optional[Transition] = None
    worldview_score: Optional[Dict[str, Any]] = None
    fusion: Optional[Dict[str, Any]] = None
    belief_updates: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    needs_reobserve: bool = False
    # Stage 3+4 scene product (dict form of WorldGraph); unused by decision scoring yet
    scene_graph: Optional[Dict[str, Any]] = None
    interaction_graph: Optional[Dict[str, Any]] = None
    capability_graph: Optional[Dict[str, Any]] = None
    held_last_good_world: bool = False
    active_subgraph: Optional[Dict[str, Any]] = None


@dataclass
class WorldModel:
    active_app: str = ""
    last_window_name: str = ""
    # Latest screenshot path seen by the world model. The multimodal perceptor
    # reasons over pixels; making the world model remember the current screenshot
    # means every perception consumer (decision synthesis, unified cognition) can
    # attach it without each call site having to thread the path through.
    last_screenshot_path: str = ""
    current_screen: Optional[Screen] = None
    entities: Dict[int, Entity] = field(default_factory=dict)
    transitions: TransitionStore = field(default_factory=TransitionStore)
    navigation_graph: NavigationGraph = field(default_factory=NavigationGraph)
    tracker: IdentityTracker = field(default_factory=IdentityTracker)
    screens: ScreenDetector = field(default_factory=ScreenDetector)
    _prev_entities: List[Entity] = field(default_factory=list)
    _prev_screen_id: Optional[int] = None
    overlay_hints: Dict[str, Any] = field(default_factory=dict)
    last_worldview_score: Dict[str, Any] = field(default_factory=dict)
    last_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    last_scene_graph: Dict[str, Any] = field(default_factory=dict)
    last_interaction_graph: Dict[str, Any] = field(default_factory=dict)
    last_capability_graph: Dict[str, Any] = field(default_factory=dict)
    last_active_subgraph: Dict[str, Any] = field(default_factory=dict)
    last_surface_state: Dict[str, Any] = field(default_factory=dict)
    last_perception_synthesis: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def _obs_is_degenerate(obs: Observation) -> bool:
        node_n = len(obs.nodes or [])
        cov = 0.0 if obs.coverage is None else max(0.0, min(1.0, float(obs.coverage)))
        if node_n <= 1:
            return True
        if cov <= 0.05:
            return True
        if obs.degraded and node_n <= 2 and cov <= 0.15:
            return True
        # A snapshot can look numerically healthy while still being semantically
        # useless if it only exposes app chrome / menus and no content-bearing
        # controls or rows. Treat those as degenerate so we preserve the last
        # good world instead of overwriting it with a partial frame.
        content_nodes = 0
        chrome_only_nodes = 0
        for node in obs.nodes or []:
            role = str(getattr(node, "role", "") or "").strip().lower()
            label = _clean_label(
                str(getattr(node, "name", "") or getattr(node, "description", "") or getattr(node, "value", "") or "")
            )
            has_content = bool(label) or bool(getattr(node, "value", None))
            if role in _CHROME_ONLY_ROLES:
                chrome_only_nodes += 1
                continue
            if has_content:
                content_nodes += 1
        if node_n >= 4 and content_nodes == 0 and chrome_only_nodes >= max(1, node_n // 2):
            return True
        return False

    def _should_hold_last_good_world(self, obs: Observation) -> bool:
        if not self.entities or self.current_screen is None:
            return False
        screen_label = _clean_label(str(getattr(self.current_screen, "label", "") or "")).lower()
        screen_kind = _clean_label(str(getattr(self.current_screen, "kind", "") or "")).lower()
        if not screen_label or screen_label.startswith("screen #"):
            return False
        if screen_kind in {"unknown", "menu_bar"}:
            return False
        if not self._obs_is_degenerate(obs):
            return False
        prev_score = self.last_worldview_score or {}
        overall = float(prev_score.get("overall", 0.0) or 0.0)
        degraded = bool(prev_score.get("degraded", False))
        if overall < 0.55 or degraded:
            return False
        # Keep a healthy world if the new snapshot carries almost no structure.
        return len(self.entities) >= 3

    def summary(self) -> Dict[str, Any]:
        """Planner-facing view — beliefs, not sensors."""
        ents = [e for e in self.entities.values() if e.visible]
        return {
            "active_app": self.active_app,
            "current_screen": None
            if not self.current_screen
            else {
                "id": self.current_screen.id,
                "label": self.current_screen.label,
                "kind": self.current_screen.kind,
                "signature": self.current_screen.signature,
            },
            "entities": [
                {
                    "id": e.id,
                    "type": e.entity_type,
                    "semantic": e.semantic_role,
                    "actions": e.actions,
                    "label": e.label,
                    "snapshots": e.snapshot_count,
                    "confidence": round(float(e.confidence), 4),
                    "beliefs": {k: v.to_dict() for k, v in (e.beliefs or {}).items()},
                }
                for e in ents
            ],
            "transition_count": len(self.transitions.transitions),
            "nav_mermaid": self.navigation_graph.to_mermaid(),
            "worldview_score": self.last_worldview_score,
            "conflicts": self.last_conflicts[:16],
            "active_subgraph": self.last_active_subgraph,
            "surface_state": self.last_surface_state,
        }

    def ingest(
        self,
        obs: Observation,
        *,
        action: Optional[str] = None,
        target_entity_id: Optional[int] = None,
        fused_frame: Any = None,
    ) -> WorldPatch:
        """Observation (or FusedFrame projection) → belief update + identity track."""
        self.active_app = obs.app_name or self.active_app
        self.last_window_name = obs.window_name or self.last_window_name
        if getattr(obs, "screenshot_path", ""):
            self.last_screenshot_path = obs.screenshot_path

        if self._should_hold_last_good_world(obs):
            screen = self.current_screen or self.screens.detect(
                [e for e in self.entities.values() if e.visible],
                application=self.active_app,
                scene_graph=self.last_scene_graph or {},
            )
            prev_score = dict(self.last_worldview_score or {})
            prev_score.setdefault("components", {})
            prev_score["held_last_good_world"] = True
            if isinstance(prev_score.get("components"), dict):
                prev_score["components"] = {
                    **(prev_score.get("components") or {}),
                    "held_last_good_world": True,
                    "observation_node_count": len(obs.nodes),
                    "observation_coverage": 0.0 if obs.coverage is None else round(float(obs.coverage), 4),
                    "observation_degraded": bool(obs.degraded),
                }
            patch = WorldPatch(
                retention=1.0,
                screen_id=screen.id,
                screen_label=screen.label,
                new_entity_ids=[],
                matched_ids=[e.id for e in self.entities.values() if e.visible],
                transition=None,
                fusion=(obs.meta or {}).get("fusion") if isinstance(obs.meta, dict) else None,
                belief_updates=[
                    {
                        "entity_id": 0,
                        "property": "world",
                        "action": "hold_last_good_world",
                        "confidence": float(prev_score.get("overall", 0.0) or 0.0),
                    }
                ],
                conflicts=list(prev_score.get("components", {}).get("conflicts") or [])[:32],
                needs_reobserve=False,
                held_last_good_world=True,
            )
            patch.worldview_score = prev_score
            self.last_worldview_score = prev_score
            self.last_conflicts = patch.conflicts
            self.current_screen = screen
            self._prev_entities = list(self.entities.values())
            self._prev_screen_id = screen.id

            try:
                from plugin.worldmodel.scene.reconstruct import reconstruct_world_graph
                from plugin.worldmodel.capability import build_capability_graph

                world_graph = reconstruct_world_graph(
                    list(self.entities.values()),
                    app=self.active_app,
                    source_patch_id=f"{screen.id}:{screen.kind or screen.label}:held",
                )
                patch.scene_graph = world_graph.to_dict()
                self.last_scene_graph = patch.scene_graph
                patch.interaction_graph = world_graph.context_graph.to_dict()
                self.last_interaction_graph = patch.interaction_graph
                cap_graph = build_capability_graph(world_graph, list(self.entities.values()), goal=None)
                patch.capability_graph = cap_graph.to_dict()
                self.last_capability_graph = patch.capability_graph
                patch.active_subgraph = dict(self.last_active_subgraph or {})
            except Exception as exc:  # noqa: BLE001 — perception must not fail ingest
                patch.scene_graph = {
                    "error": str(exc),
                    "regions": [],
                    "report": {"notes": ["scene_reconstruct_failed"]},
                }
                self.last_scene_graph = patch.scene_graph
                patch.interaction_graph = {"nodes": [], "edges": []}
                self.last_interaction_graph = patch.interaction_graph
                patch.capability_graph = {
                    "nodes": {},
                    "edges": [],
                    "frontier": [],
                    "goal_kind": "",
                    "goal_capability_ids": [],
                    "interaction_graph": patch.interaction_graph,
                }
                self.last_capability_graph = patch.capability_graph
                patch.active_subgraph = dict(self.last_active_subgraph or {})
            return patch

        raw = entities_from_observation(obs)
        apply_cached_semantics(raw)
        # Attach beliefs from projected node attributes / fused frame
        self._seed_beliefs_from_observation(raw, obs, fused_frame=fused_frame)

        prev_by_key = {
            (e.entity_key or f"{e.entity_type}|{_clean_label(e.label).lower()}"): e
            for e in self.entities.values()
        }

        match: MatchResult = self.tracker.update(raw)
        # Soft-delete: entities missing this frame decay exists belief; drop after N misses
        belief_updates: List[Dict[str, Any]] = []
        seen_ids = set(match.matched_prev_ids) | set(match.new_ids)
        tracked_map = {e.id: e for e in match.tracked}

        for eid, old in list(self.tracker.entities.items()):
            if eid in tracked_map:
                continue
            # Not rematched — decay rather than immediate delete
            old.miss_frames = int(old.miss_frames or 0) + 1
            exists = old.beliefs.get("exists")
            if exists is None:
                exists = Belief(value=True, confidence=0.6)
            exists = exists.decay(0.85)
            old.beliefs["exists"] = exists
            old.confidence = min(old.confidence, exists.confidence)
            belief_updates.append(
                {"entity_id": eid, "property": "exists", "action": "decay", "confidence": exists.confidence}
            )
            if exists.confidence < EXISTS_DROP_CONFIDENCE or old.miss_frames >= SOFT_DELETE_MISS_FRAMES:
                # allow tracker to drop on next hard replace; mark invisible
                old.visible = False
                belief_updates.append({"entity_id": eid, "property": "exists", "action": "soft_delete"})

        # Merge belief state onto tracked entities
        for e in match.tracked:
            e.miss_frames = 0
            key = e.entity_key or f"{e.entity_type}|{_clean_label(e.label).lower()}"
            e.entity_key = key
            prev = prev_by_key.get(key)
            if prev and prev.beliefs:
                for prop, bel in prev.beliefs.items():
                    if prop not in e.beliefs:
                        e.beliefs[prop] = bel.decay(0.95)
                    else:
                        e.beliefs[prop] = bel.blend(
                            e.beliefs[prop].value,
                            e.beliefs[prop].confidence,
                            source="ingest",
                            prop=prop,
                        )
            if "exists" not in e.beliefs:
                e.beliefs["exists"] = Belief(value=True, confidence=float(e.confidence or 0.8))
            if "label" not in e.beliefs:
                e.beliefs["label"] = Belief(value=e.label, confidence=float(e.confidence or 0.8))
            # Sync scalar fields from beliefs
            lab_b = e.beliefs.get("label")
            if isinstance(lab_b, dict):
                lab_b = Belief.from_dict(lab_b)
                e.beliefs["label"] = lab_b
            if lab_b is not None and lab_b.value:
                e.label = str(lab_b.value)
                e.semantic_role = e.semantic_role or e.label
            vis_b = e.beliefs.get("visible")
            if isinstance(vis_b, dict):
                vis_b = Belief.from_dict(vis_b)
                e.beliefs["visible"] = vis_b
            if vis_b is not None:
                e.visible = bool(vis_b.value) and e.visible
            # Ensure all beliefs are Belief objects
            for prop, bel in list(e.beliefs.items()):
                if isinstance(bel, dict):
                    e.beliefs[prop] = Belief.from_dict(bel)
                elif not isinstance(bel, Belief):
                    e.beliefs[prop] = Belief(value=bel, confidence=0.5)
            e.confidence = float(
                0.5 * e.belief_confidence("exists", e.confidence)
                + 0.5 * e.belief_confidence("label", e.confidence)
            )
            belief_updates.append(
                {"entity_id": e.id, "property": "*", "action": "update", "confidence": e.confidence}
            )

        # Keep soft-missing entities still within miss budget
        merged = dict(self.tracker.entities)
        for old in list(self.entities.values()):
            if old.id in merged:
                continue
            if (
                old.miss_frames < SOFT_DELETE_MISS_FRAMES
                and old.belief_confidence("exists", 0) >= EXISTS_DROP_CONFIDENCE
            ):
                merged[old.id] = old
        for e in match.tracked:
            merged[e.id] = e
        if hasattr(self.tracker, "_entities"):
            self.tracker._entities = merged  # type: ignore[attr-defined]
        self.entities = dict(merged)

        screen = self.screens.detect(
            [e for e in self.entities.values() if e.visible],
            application=self.active_app,
            scene_graph=self.last_scene_graph or {},
        )
        transition = None
        if (
            action
            and self._prev_screen_id is not None
            and self._prev_screen_id != screen.id
        ):
            diff = compute_entity_diff(self._prev_entities, list(self.entities.values()))
            transition = self.transitions.record(
                from_screen=self._prev_screen_id,
                to_screen=screen.id,
                action=action,
                target_entity_id=target_entity_id,
                diff=diff,
            )
            self.navigation_graph.sync_from_store(self.transitions.transitions)

        self._prev_entities = list(self.entities.values())
        self._prev_screen_id = screen.id
        self.current_screen = screen

        fusion_meta = (obs.meta or {}).get("fusion") if isinstance(obs.meta, dict) else None
        if fused_frame is not None and hasattr(fused_frame, "report"):
            fusion_meta = fused_frame.report.to_dict()
        agreement = None
        conflicts: List[Dict[str, Any]] = []
        needs = False
        if isinstance(fusion_meta, dict):
            agreement = fusion_meta.get("agreement")
            conflicts = list(fusion_meta.get("conflicts") or [])
            needs = bool(fusion_meta.get("needs_reobserve"))
        self.last_conflicts = conflicts

        from plugin.worldmodel.score import compute_worldview_score

        patch = WorldPatch(
            retention=match.retention,
            screen_id=screen.id,
            screen_label=screen.label,
            new_entity_ids=match.new_ids,
            matched_ids=match.matched_prev_ids,
            transition=transition,
            fusion=fusion_meta if isinstance(fusion_meta, dict) else None,
            belief_updates=belief_updates[:64],
            conflicts=conflicts[:32],
            needs_reobserve=needs,
        )
        score = compute_worldview_score(
            obs,
            patch,
            source_agreement=float(agreement) if agreement is not None else None,
            fusion_meta=fusion_meta if isinstance(fusion_meta, dict) else None,
            entities=list(self.entities.values()),
        )
        patch.worldview_score = score.to_dict()
        patch.needs_reobserve = bool(score.needs_reobserve or needs)
        self.last_worldview_score = score.to_dict()

        # Stage 3+4: geometry/AX layout + contains graph (no scoring impact yet)
        try:
            from plugin.worldmodel.scene.reconstruct import reconstruct_world_graph
            from plugin.worldmodel.capability import build_capability_graph

            world_graph = reconstruct_world_graph(
                list(self.entities.values()),
                app=self.active_app,
                source_patch_id=f"{screen.id}:{screen.kind or screen.label}",
            )
            patch.scene_graph = world_graph.to_dict()
            self.last_scene_graph = patch.scene_graph
            patch.interaction_graph = world_graph.context_graph.to_dict()
            self.last_interaction_graph = patch.interaction_graph
            cap_graph = build_capability_graph(world_graph, list(self.entities.values()), goal=None)
            patch.capability_graph = cap_graph.to_dict()
            self.last_capability_graph = patch.capability_graph
            patch.active_subgraph = dict(self.last_active_subgraph or {})
        except Exception as exc:  # noqa: BLE001 — perception must not fail ingest
            patch.scene_graph = {
                "error": str(exc),
                "regions": [],
                "report": {"notes": ["scene_reconstruct_failed"]},
            }
            self.last_scene_graph = patch.scene_graph
            patch.interaction_graph = {"nodes": [], "edges": []}
            self.last_interaction_graph = patch.interaction_graph
            patch.capability_graph = {
                "nodes": {},
                "edges": [],
                "frontier": [],
                "goal_kind": "",
                "goal_capability_ids": [],
                "interaction_graph": patch.interaction_graph,
            }
            self.last_capability_graph = patch.capability_graph
            patch.active_subgraph = dict(self.last_active_subgraph or {})

        return patch

    def ingest_fused_frame(self, frame: Any, *, action: Optional[str] = None) -> WorldPatch:
        """Preferred entry: fuse first, then belief ingest."""
        obs = frame.to_observation()
        return self.ingest(obs, action=action, fused_frame=frame)

    def _seed_beliefs_from_observation(
        self,
        entities: List[Entity],
        obs: Observation,
        *,
        fused_frame: Any = None,
    ) -> None:
        by_key: Dict[str, Any] = {}
        if fused_frame is not None:
            for fe in getattr(fused_frame, "entities", []) or []:
                by_key[fe.key] = fe
                # also label-only key
                by_key[f"{fe.role}|{_clean_label(fe.label).lower()}"] = fe

        for e in entities:
            attrs = e.attributes or {}
            key = str(attrs.get("entity_key") or "")
            if not key:
                key = f"{e.entity_type}|{_clean_label(e.label).lower()}"
            e.entity_key = key
            fe = by_key.get(key)
            if fe is not None and getattr(fe, "beliefs", None):
                e.beliefs = dict(fe.beliefs)
                e.confidence = float(fe.confidence)
                e.evidence = [
                    {"source": s, "property": "exists", "confidence": fe.confidence}
                    for s in (fe.sources or [])
                ]
                continue
            # From projected belief_* attrs
            beliefs: Dict[str, Belief] = {}
            for ak, av in attrs.items():
                if ak.startswith("belief_") and isinstance(av, dict):
                    prop = ak[len("belief_") :]
                    beliefs[prop] = Belief.from_dict(av)
            if not beliefs:
                conf = float(attrs.get("belief_confidence") or 0.85)
                beliefs["exists"] = Belief(value=True, confidence=conf)
                beliefs["label"] = Belief(value=e.label, confidence=conf)
                beliefs["visible"] = Belief(value=True, confidence=conf)
            e.beliefs = beliefs
            e.confidence = float(attrs.get("belief_confidence") or (
                0.5 * e.belief_confidence("exists", 0.8) + 0.5 * e.belief_confidence("label", 0.8)
            ))
            e.evidence = [
                {"source": s, "property": "observed"}
                for s in (attrs.get("sources") or [obs.source])
            ]

    def find_entity(self, semantic: str) -> Optional[Entity]:
        """Resolve by label/semantic. Exact match wins over substring."""
        sem = _clean_label(semantic).lower()
        if not sem:
            return None

        exact: List[Entity] = []
        substring: List[Entity] = []
        for e in self.entities.values():
            if not e.visible:
                continue
            role = _clean_label(e.semantic_role or "").lower()
            lab = _clean_label(e.label or "").lower()
            if role == sem or lab == sem:
                exact.append(e)
            elif sem in role or sem in lab:
                substring.append(e)

        prefer_order = ("button", "textfield", "link", "menu", "static", "list", "group", "unknown")

        def _pick(cands: List[Entity]) -> Optional[Entity]:
            if not cands:
                return None
            # Prefer higher belief confidence
            cands = sorted(cands, key=lambda e: -float(e.confidence))
            for pref in prefer_order:
                for e in cands:
                    if e.entity_type == pref:
                        return e
            return cands[0]

        hit = _pick(exact)
        if hit is not None:
            return hit
        substring.sort(
            key=lambda e: (
                -float(e.confidence),
                len(_clean_label(e.label or e.semantic_role or "")),
                prefer_order.index(e.entity_type) if e.entity_type in prefer_order else 99,
            )
        )
        return substring[0] if substring else None
