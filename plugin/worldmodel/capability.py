"""Capability graph, grounding, and frontier search for the world model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.worldmodel.scene import RegionKind, WorldGraph
from plugin.worldmodel.scene.reconstruct import (
    region_id_for_entity,
    region_ids_for_entity,
    region_kind_for_entity,
)


def _looks_like_openable_label(name: str) -> bool:
    n = _clean_label(name)
    if not n or len(n) > 48:
        return False
    low = n.lower()
    if low in {
        "search",
        "search results",
        "chats",
        "calls",
        "status",
        "settings",
        "more",
        "menu",
        "back",
    }:
        return False
    if any(marker in low for marker in ("message,", "created this group", "voice message", "end-to-end encrypted")):
        return False
    return True


@dataclass
class Capability:
    capability_id: str
    type: str
    confidence: float = 0.0
    provider_entities: List[int] = field(default_factory=list)
    provider_regions: List[str] = field(default_factory=list)
    predicted_transition: str = ""
    risk: float = 0.0
    reversibility: bool = True
    evidence: Dict[str, Any] = field(default_factory=dict)
    visible: bool = True
    parent_capability_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Capability":
        return cls(
            capability_id=str(data.get("capability_id") or ""),
            type=str(data.get("type") or ""),
            confidence=float(data.get("confidence") or 0.0),
            provider_entities=[int(x) for x in (data.get("provider_entities") or [])],
            provider_regions=[str(x) for x in (data.get("provider_regions") or [])],
            predicted_transition=str(data.get("predicted_transition") or ""),
            risk=float(data.get("risk") or 0.0),
            reversibility=bool(data.get("reversibility", True)),
            evidence=dict(data.get("evidence") or {}),
            visible=bool(data.get("visible", True)),
            parent_capability_id=str(data.get("parent_capability_id") or ""),
        )


@dataclass
class CapabilityEdge:
    source_id: str
    target_id: str
    kind: str = "depends_on"
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilityEdge":
        return cls(
            source_id=str(data.get("source_id") or ""),
            target_id=str(data.get("target_id") or ""),
            kind=str(data.get("kind") or "depends_on"),
            confidence=float(data.get("confidence") or 1.0),
        )


@dataclass
class FrontierNode:
    capability_id: str
    type: str
    reason: str = ""
    parent_capability_id: str = ""
    region_id: str = ""
    entity_ids: List[int] = field(default_factory=list)
    confidence: float = 0.0
    risk: float = 0.0
    depth: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FrontierNode":
        return cls(
            capability_id=str(data.get("capability_id") or ""),
            type=str(data.get("type") or ""),
            reason=str(data.get("reason") or ""),
            parent_capability_id=str(data.get("parent_capability_id") or ""),
            region_id=str(data.get("region_id") or ""),
            entity_ids=[int(x) for x in (data.get("entity_ids") or [])],
            confidence=float(data.get("confidence") or 0.0),
            risk=float(data.get("risk") or 0.0),
            depth=int(data.get("depth") or 0),
        )


@dataclass
class GroundedAction:
    capability_id: str
    capability_type: str
    entity_id: Optional[int] = None
    confidence: float = 0.0
    reason: str = ""
    expected_transition: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilityMemory:
    successful_trajectories: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    def record_success(
        self,
        *,
        goal_kind: str,
        capability_id: str,
        entity_id: Optional[int],
        world_id: str = "",
        outcome: str = "",
    ) -> None:
        key = goal_kind or "unknown"
        self.successful_trajectories.setdefault(key, []).append(
            {
                "capability_id": capability_id,
                "entity_id": entity_id,
                "world_id": world_id,
                "outcome": outcome,
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilityGraph:
    nodes: Dict[str, Capability] = field(default_factory=dict)
    edges: List[CapabilityEdge] = field(default_factory=list)
    frontier: List[FrontierNode] = field(default_factory=list)
    goal_kind: str = ""
    goal_capability_ids: List[str] = field(default_factory=list)
    interaction_graph: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "frontier": [f.to_dict() for f in self.frontier],
            "goal_kind": self.goal_kind,
            "goal_capability_ids": list(self.goal_capability_ids),
            "interaction_graph": dict(self.interaction_graph),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilityGraph":
        nodes = {
            str(k): Capability.from_dict(v)
            for k, v in (data.get("nodes") or {}).items()
            if isinstance(v, dict)
        }
        return cls(
            nodes=nodes,
            edges=[CapabilityEdge.from_dict(x) for x in (data.get("edges") or [])],
            frontier=[FrontierNode.from_dict(x) for x in (data.get("frontier") or [])],
            goal_kind=str(data.get("goal_kind") or ""),
            goal_capability_ids=[str(x) for x in (data.get("goal_capability_ids") or [])],
            interaction_graph=dict(data.get("interaction_graph") or {}),
        )

    def visible_capabilities(self) -> List[Capability]:
        return [cap for cap in self.nodes.values() if cap.visible]

    def select_for_goal(self, goal: Any) -> Optional[Capability]:
        wanted = set(goal_capability_types(goal))
        if not wanted:
            return None

        visible = [cap for cap in self.nodes.values() if cap.visible and cap.type in wanted]
        if visible:
            return max(visible, key=lambda c: _capability_rank(c, goal))

        frontier_caps = [
            self.nodes.get(node.capability_id)
            for node in self.frontier
            if node.capability_id in self.nodes and self.nodes[node.capability_id].type in wanted
        ]
        frontier_caps = [cap for cap in frontier_caps if cap is not None]
        if frontier_caps:
            return max(frontier_caps, key=lambda c: _capability_rank(c, goal))
        return None

    def select_frontier(self, goal: Any) -> List[FrontierNode]:
        wanted = set(goal_capability_types(goal))
        if not wanted:
            return list(self.frontier)
        return [node for node in self.frontier if node.type in wanted]

    def capability_for_action(
        self,
        *,
        action_family: str,
        semantic_target: str = "",
        text: str = "",
    ) -> Optional[Capability]:
        wanted = action_family_to_capability_type(action_family, semantic_target=semantic_target, text=text)
        if not wanted:
            return None
        cands = [
            cap
            for cap in self.nodes.values()
            if cap.type == wanted
            and cap.visible
            and _capability_matches_action(
                cap,
                action_family=action_family,
                semantic_target=semantic_target,
                text=text,
            )
        ]
        if not cands:
            cands = [
                cap
                for cap in self.nodes.values()
                if cap.type == wanted
                and _capability_matches_action(
                    cap,
                    action_family=action_family,
                    semantic_target=semantic_target,
                    text=text,
                )
            ]
        if not cands:
            return None
        return max(cands, key=lambda c: (float(c.visible), float(c.confidence), -float(c.risk)))


_AFFORDANCE_TO_CAPABILITY: Dict[str, str] = {
    "initiate_voice": "InitiateVoiceCall",
    "initiate_video": "InitiateVideoCall",
    "select_participants": "SelectParticipants",
    "open_call_menu": "RevealCommunicationOptions",
    "probe_hover": "RevealHiddenActions",
    "probe_context_menu": "RevealHiddenActions",
    "probe_focus": "ProbeSurface",
    "forward_message": "ForwardMessage",
    "compose_text": "ComposeMessage",
    "attach_media": "AttachMedia",
    "send_message": "SendMessage",
    "choose_option": "ChooseOption",
    "initiate_session": "InitiateVoiceCall",
    "confirm": "ConfirmAction",
    "dismiss": "DismissOverlay",
    "navigate": "Navigate",
    "open_menu": "OpenMenu",
    "select_item": "SelectConversation",
    "scroll_content": "ScrollContent",
    "status_read": "ReadStatus",
    "unknown": "UnknownCapability",
    "search": "SearchConversation",
}


def _label_based_capability_types(entity: Entity, region_kind: Optional[RegionKind]) -> List[str]:
    from plugin.agent.apps.whatsapp_semantics import entity_semantic_type
    from plugin.worldmodel.pragmatic_role import (
        UiPragmaticRole,
        get_pragmatic_role,
        infer_pragmatic_role_stage2,
    )

    if get_pragmatic_role(entity) == UiPragmaticRole.UNKNOWN:
        infer_pragmatic_role_stage2(entity)
    role = get_pragmatic_role(entity)
    sem_type = _clean_label(str(entity_semantic_type(entity)[0] or "")).lower()
    ax_role = _clean_label(getattr(entity, "role", "") or "").lower()

    label = _clean_label(entity.label or entity.semantic_role or "").lower()
    desc = _clean_label(str(entity.attributes.get("description") or entity.attributes.get("AXDescription") or "")).lower()
    blob = _clean_label(f"{entity.label} {entity.semantic_role} {entity.entity_type} {desc}").lower()
    kinds: List[str] = []
    interactive = bool(entity.actions) or entity.entity_type in {"button", "link", "menu", "textfield"}
    in_chrome = region_kind in {
        RegionKind.FLOATING_MENU,
        RegionKind.MODAL,
        RegionKind.HEADER,
        RegionKind.TOOLBAR,
    }

    # Global menu-bar chrome must never generate content capabilities. Those
    # nodes are shell affordances, not WhatsApp conversation surfaces.
    if entity.entity_type in {"menu", "menubar"} or ax_role in {"axmenuitem", "axmenubar", "axmenubaritem"}:
        return list(dict.fromkeys(kinds))

    # Nav chrome never initiates calls / open conversation from tab labels
    if role == UiPragmaticRole.NAV_CHROME:
        kinds.append("Navigate")
        return list(dict.fromkeys(kinds))

    if role == UiPragmaticRole.STATUS:
        kinds.append("ReadStatus")
        return list(dict.fromkeys(kinds))

    if role == UiPragmaticRole.CTA or role == UiPragmaticRole.UNKNOWN:
        if interactive and "voice" in blob and "message" not in blob and (
            "call" in blob or label == "voice" or (label == "audio call")
        ):
            kinds.append("InitiateVoiceCall")
        elif (
            interactive
            and "voice" in blob
            and "message" not in blob
            and in_chrome
        ):
            kinds.append("InitiateVoiceCall")
        if interactive and entity.entity_type == "button" and label == "video" and in_chrome:
            kinds.append("InitiateVideoCall")
        if interactive and "video" in blob and "call" in blob and in_chrome:
            kinds.append("InitiateVideoCall")
        if interactive and entity.entity_type == "button" and label in {
            "cancel",
            "ok",
            "close",
            "later",
            "not now",
            "don't allow",
            "allow",
        }:
            kinds.append("DismissOverlay")
        if interactive and label in {"more", "menu", "options", "more options"}:
            kinds.append("OpenMenu")
        if interactive and ("select people" in blob or "add people" in blob or "participant" in blob):
            kinds.append("SelectParticipants")
        if interactive and ("call dropdown" in blob or "call menu" in blob or "open call dropdown" in blob):
            kinds.append("RevealCommunicationOptions")

    if "search" in blob and entity.entity_type in {"textfield", "static", "button", "cell"}:
        if role in {UiPragmaticRole.INPUT, UiPragmaticRole.CTA, UiPragmaticRole.UNKNOWN}:
            kinds.append("SearchConversation")
    if entity.entity_type == "textfield" and (
        "search" in blob
        or (
            region_kind in {RegionKind.SIDEBAR, RegionKind.HEADER, RegionKind.TOOLBAR}
            and "compose" not in blob
        )
    ):
        kinds.append("SearchConversation")
    if sem_type == "call_button":
        if interactive and ("video" in blob and "call" in blob or label == "video"):
            kinds.append("InitiateVideoCall")
        if interactive and "voice" in blob and "message" not in blob and (
            "call" in blob or label == "voice" or label == "audio call"
        ):
            kinds.append("InitiateVoiceCall")
        if interactive and ("select people" in blob or "add people" in blob or "participant" in blob):
            kinds.append("SelectParticipants")
        if interactive and ("call dropdown" in blob or "call menu" in blob or "open call dropdown" in blob):
            kinds.append("RevealCommunicationOptions")
        return list(dict.fromkeys(kinds))

    if entity.entity_type in {"button", "static", "cell", "link"} and role in {
        UiPragmaticRole.CONTENT,
        UiPragmaticRole.CTA,
        UiPragmaticRole.UNKNOWN,
    }:
        contactish = any(token in blob for token in ("group", "chat", "contact", "messages", "conversation"))
        desc_contactish = _looks_like_openable_label(desc)
        nameish = (
            "search" not in blob
            and "voice" not in blob
            and "video" not in blob
            and "call" not in blob
            and "settings" not in blob
            and len([t for t in blob.split() if t]) <= 4
        )
        generic = {
            "chats",
            "search",
            "updates",
            "status",
            "settings",
            "calls",
            "new chat",
            "chat",
        }
        if (contactish or desc_contactish or (
            nameish and _clean_label(entity.label or entity.semantic_role or "").lower() not in generic
        )) and sem_type != "call_button":
            kinds.append("OpenConversation")
        if (
            interactive
            and in_chrome
            and ("call" in blob or label == "voice" or label == "video" or "select people" in blob)
            and "message" not in blob
        ):
            if "voice" in blob or label == "voice":
                kinds.append("InitiateVoiceCall")
            if "video" in blob or label == "video":
                kinds.append("InitiateVideoCall")
            if "select people" in blob or "participant" in blob:
                kinds.append("SelectParticipants")
    return list(dict.fromkeys(kinds))


def goal_capability_types(goal: Any) -> List[str]:
    kind = str(getattr(goal, "kind", goal) or "")
    kind_l = kind.lower()
    if any(token in kind_l for token in ("call", "voice", "video", "phone", "ring")):
        return [
            "InitiateVoiceCall",
            "RevealCommunicationOptions",
            "InitiateVideoCall",
            "SelectParticipants",
            "OpenMenu",
            "OpenConversation",
        ]
    if any(token in kind_l for token in ("forward", "share", "send")):
        return ["ForwardMessage", "OpenConversation", "SearchConversation", "OpenMenu"]
    if any(token in kind_l for token in ("message", "chat", "compose", "send", "reply", "mail")):
        return ["SendMessage", "ComposeMessage", "OpenConversation", "OpenMenu"]
    if any(token in kind_l for token in ("search", "find", "lookup")):
        return ["SearchConversation", "OpenSearch", "OpenMenu"]
    if any(token in kind_l for token in ("settings", "pref", "config")):
        return ["OpenMenu", "Navigate", "NavigateBack"]
    return ["Navigate", "OpenMenu", "UnknownCapability"]


def action_family_to_capability_type(
    action_family: str,
    *,
    semantic_target: str = "",
    text: str = "",
) -> str:
    fam = str(action_family or "").lower()
    sem = _clean_label(semantic_target or "").lower()
    txt = _clean_label(text or "").lower()
    blob = f"{sem} {txt}"
    if fam == "start_call":
        if any(token in blob for token in ("video",)):
            return "InitiateVideoCall"
        if any(token in blob for token in ("people", "participant")):
            return "SelectParticipants"
        if any(token in blob for token in ("menu", "more", "dropdown")):
            return "RevealCommunicationOptions"
        return "InitiateVoiceCall"
    if fam == "forward_message":
        return "ForwardMessage"
    if fam == "open_source_chat":
        return "OpenConversation"
    if fam == "open_contact":
        return "OpenConversation"
    if fam == "type_query":
        return "SearchConversation"
    if fam == "open_search":
        return "OpenSearch"
    if fam == "probe_hover":
        return "RevealHiddenActions"
    if fam == "probe_context_menu":
        return "RevealHiddenActions"
    if fam == "probe_focus":
        return "ProbeSurface"
    if fam == "dismiss":
        return "DismissOverlay"
    if fam == "end_call":
        return "DismissOverlay"
    if fam == "observe":
        return "Observe"
    if fam == "explore_chrome":
        return "OpenMenu"
    return _AFFORDANCE_TO_CAPABILITY.get(fam, "UnknownCapability")


def _capability_predicted_transition(capability_type: str) -> str:
    return {
        "InitiateVoiceCall": "move into ringing/call state",
        "InitiateVideoCall": "move into video call state",
        "RevealCommunicationOptions": "reveal secondary call controls",
        "RevealHiddenActions": "reveal hidden surface actions",
        "ProbeSurface": "probe latent surface affordances",
        "SelectParticipants": "open participant selection",
        "ForwardMessage": "open forward destination picker",
        "OpenConversation": "open target conversation",
        "SearchConversation": "surface search results",
        "OpenSearch": "focus search surface",
        "OpenMenu": "reveal menu options",
        "SendMessage": "append message to composer",
        "ComposeMessage": "focus composer input",
        "DismissOverlay": "remove overlay surface",
        "NavigateBack": "return to previous surface",
    }.get(capability_type, "change current surface")


def _capability_reversible(capability_type: str, region_kind: Optional[RegionKind]) -> bool:
    if capability_type in {
        "DismissOverlay",
        "NavigateBack",
        "OpenMenu",
        "RevealCommunicationOptions",
        "RevealHiddenActions",
        "ProbeSurface",
        "SelectParticipants",
    }:
        return True
    if region_kind in {RegionKind.FLOATING_MENU, RegionKind.MODAL, RegionKind.TOOLBAR}:
        return True
    return capability_type not in {"InitiateVoiceCall", "InitiateVideoCall", "SendMessage", "ForwardMessage"}


def _capability_risk(capability_type: str, region_kind: Optional[RegionKind]) -> float:
    if capability_type in {"InitiateVoiceCall", "InitiateVideoCall"}:
        return 0.35 if region_kind in {RegionKind.FLOATING_MENU, RegionKind.MODAL} else 0.55
    if capability_type in {"ForwardMessage"}:
        return 0.42 if region_kind in {RegionKind.FLOATING_MENU, RegionKind.MODAL} else 0.58
    if capability_type in {"SendMessage"}:
        return 0.45
    if capability_type in {"RevealHiddenActions", "ProbeSurface"}:
        return 0.1
    if capability_type in {"DismissOverlay"}:
        return 0.08
    if capability_type in {"OpenConversation", "SearchConversation", "OpenSearch"}:
        return 0.12
    return 0.18


def _capability_rank(capability: Capability, goal: Any) -> Tuple[float, float, float, int]:
    wanted = goal_capability_types(goal)
    try:
        idx = wanted.index(capability.type)
    except ValueError:
        idx = len(wanted)
    visible_bonus = 1.0 if capability.visible else 0.0
    return (
        visible_bonus,
        -float(idx),
        float(capability.confidence) - float(capability.risk),
        -len(capability.provider_entities),
    )


def _goal_node_id(goal: Any) -> str:
    return f"goal:{str(getattr(goal, 'kind', goal) or 'unknown').strip().lower()}"


def _capability_entity_blob(capability: Capability) -> str:
    evidence = capability.evidence if isinstance(capability.evidence, dict) else {}
    parts = [
        str(capability.type or ""),
        str(capability.predicted_transition or ""),
        str(evidence.get("entity_label") or ""),
        str(evidence.get("entity_type") or ""),
        str(evidence.get("region_kind") or ""),
    ]
    return _clean_label(" ".join(parts)).lower()


def _capability_matches_action(
    capability: Capability,
    *,
    action_family: str,
    semantic_target: str = "",
    text: str = "",
) -> bool:
    fam = str(action_family or "").strip().lower()
    target = _clean_label(semantic_target or "").lower()
    blob = _capability_entity_blob(capability)
    label = str((capability.evidence or {}).get("entity_label") or "").strip().lower()

    if fam in {"type_query", "open_search"}:
        if capability.type not in {"SearchConversation", "OpenSearch"}:
            return False
        if any(token in blob for token in ("settings", "call", "video", "voice", "status")):
            return False
        if target and target not in {"search", "search conversation", "search results"}:
            return False
        return any(token in blob for token in ("search", "query", "find", "look up", "start new chat")) or "search" in label

    if fam == "open_contact":
        if capability.type != "OpenConversation":
            return False
        if any(token in blob for token in ("settings", "call", "video", "voice", "menu", "more", "search")):
            return False
        return True

    if fam == "select_content":
        return capability.type in {"OpenConversation", "RevealHiddenActions", "ProbeSurface", "ForwardMessage"} and any(
            token in blob for token in ("message", "timeline", "conversation", "chat", "row", "card", "link")
        )

    if fam in {"forward_message", "select_forward_target"}:
        if capability.type != "ForwardMessage":
            return False
        return any(token in blob for token in ("forward", "message", "share", "picker", "dropdown")) or "forward" in label

    if fam in {"probe_hover", "probe_context_menu", "probe_focus"}:
        return capability.type in {"RevealHiddenActions", "ProbeSurface"} and any(
            token in blob for token in ("message", "row", "card", "conversation", "timeline", "chat")
        )

    if fam == "start_call":
        if capability.type not in {"InitiateVoiceCall", "InitiateVideoCall", "SelectParticipants", "RevealCommunicationOptions"}:
            return False
        if any(token in blob for token in ("voice", "audio", "video", "call", "participant", "people", "dropdown", "menu")):
            return True
        return "call" in label

    if fam in {"dismiss", "end_call"}:
        return capability.type == "DismissOverlay"

    if fam == "observe":
        return capability.type == "Observe"

    if fam == "explore_chrome":
        return capability.type == "OpenMenu" and not any(token in blob for token in ("search", "query"))

    return True


def _validate_grounded_entity(capability: Capability, entity: Entity) -> bool:
    if entity is None or not entity.visible:
        return False
    label = _clean_label(entity.label or entity.semantic_role or "").lower()
    desc = _clean_label(str(entity.attributes.get("description") or entity.attributes.get("AXDescription") or "")).lower()
    blob = _clean_label(f"{entity.label} {entity.semantic_role} {entity.entity_type} {desc} {entity.role}").lower()

    if capability.type in {"SearchConversation", "OpenSearch"}:
        if "search" not in blob and "query" not in blob and "find" not in blob and "start new chat" not in blob:
            return False
        if any(token in blob for token in ("settings", "more options", "menu", "call", "video", "voice")):
            return False
        return entity.entity_type in {"textfield", "button", "static", "cell", "menu"}

    if capability.type == "OpenConversation":
        if any(token in blob for token in ("search", "settings", "call", "video", "voice", "more options")):
            return False
        return entity.entity_type in {"button", "static", "cell", "link"} or "chat" in blob or "conversation" in blob

    if capability.type == "ForwardMessage":
        if any(token in blob for token in ("search", "settings")):
            return False
        return "forward" in blob or "message" in blob or entity.entity_type in {"button", "menu", "static", "cell"}

    if capability.type in {"RevealHiddenActions", "ProbeSurface"}:
        return entity.entity_type in {"button", "static", "cell", "link"}

    if capability.type in {"InitiateVoiceCall", "InitiateVideoCall", "SelectParticipants", "RevealCommunicationOptions"}:
        return any(token in blob for token in ("voice", "video", "call", "participant", "people", "dropdown", "menu"))

    return True


def project_capability_graph(
    graph: CapabilityGraph,
    *,
    active_entity_ids: Optional[Iterable[int]] = None,
    focus_region_ids: Optional[Iterable[str]] = None,
    goal: Any = None,
) -> CapabilityGraph:
    """Return a physically smaller graph for the currently active reasoning scope."""

    active_entity_set = {int(eid) for eid in (active_entity_ids or [])}
    focus_region_set = {str(rid).strip() for rid in (focus_region_ids or []) if str(rid).strip()}
    goal_types = set(goal_capability_types(goal))
    keep: set[str] = set()

    for cap in graph.nodes.values():
        if cap.capability_id in graph.goal_capability_ids:
            keep.add(cap.capability_id)
            continue
        if cap.type in goal_types and cap.visible:
            keep.add(cap.capability_id)
            continue
        if active_entity_set and any(eid in active_entity_set for eid in cap.provider_entities):
            keep.add(cap.capability_id)
            continue
        if focus_region_set and any(rid in focus_region_set for rid in cap.provider_regions):
            keep.add(cap.capability_id)
            continue

    for frontier in graph.frontier:
        if frontier.capability_id in graph.nodes and frontier.type in goal_types:
            keep.add(frontier.capability_id)

    changed = True
    while changed:
        changed = False
        for cap_id in list(keep):
            cap = graph.nodes.get(cap_id)
            if cap is None or not cap.parent_capability_id:
                continue
            if cap.parent_capability_id not in keep:
                keep.add(cap.parent_capability_id)
                changed = True
        for edge in graph.edges:
            if edge.target_id in keep and edge.source_id in graph.nodes and edge.source_id not in keep:
                keep.add(edge.source_id)
                changed = True

    projected = CapabilityGraph(
        nodes={cap_id: graph.nodes[cap_id] for cap_id in keep if cap_id in graph.nodes},
        edges=[edge for edge in graph.edges if edge.source_id in keep and edge.target_id in keep],
        frontier=[node for node in graph.frontier if node.capability_id in keep],
        goal_kind=graph.goal_kind,
        goal_capability_ids=[cap_id for cap_id in graph.goal_capability_ids if cap_id in keep],
        interaction_graph=dict(graph.interaction_graph),
    )
    return projected


def build_capability_graph(
    graph: WorldGraph,
    entities: Sequence[Entity],
    goal: Optional[Any] = None,
    capability_hints: Optional[Dict[str, Any]] = None,
) -> CapabilityGraph:
    """Turn scene affordances into explicit capability hypotheses and frontier."""

    hints = capability_hints or {}
    label_hints: Dict[str, List[str]] = {}
    for key, value in (hints.get("label_capability_types") or {}).items():
        norm = _clean_label(key).lower()
        if not norm:
            continue
        vals = value if isinstance(value, (list, tuple, set)) else [value]
        label_hints[norm] = [str(v) for v in vals if str(v)]
    label_regions: Dict[str, List[str]] = {}
    for key, value in (hints.get("label_capability_regions") or {}).items():
        norm = _clean_label(key).lower()
        if not norm:
            continue
        vals = value if isinstance(value, (list, tuple, set)) else [value]
        label_regions[norm] = [str(v).lower() for v in vals if str(v)]
    goal_hints: Dict[str, List[str]] = {}
    for key, value in (hints.get("goal_capability_types") or {}).items():
        k = str(key)
        vals = value if isinstance(value, (list, tuple, set)) else [value]
        goal_hints[k] = [str(v) for v in vals if str(v)]

    by_id = {e.id: e for e in entities if e.visible}
    capability_graph = CapabilityGraph(
        goal_kind=str(getattr(goal, "kind", "") or ""),
        interaction_graph=graph.context_graph.to_dict(),
    )
    visible_goal_caps: List[str] = []
    region_caps: Dict[str, List[str]] = {}
    visible_types: Dict[str, List[str]] = {}
    latent_probe_types = {"RevealHiddenActions", "ProbeSurface"}

    for eid, entity in by_id.items():
        hyps = list(graph.affordances.hypotheses_for(eid))
        region_ids = region_ids_for_entity(graph, eid)
        region_id = region_ids[0] if region_ids else ""
        region_kind = region_kind_for_entity(graph, eid)
        region_caps.setdefault(region_id, [])
        visible_types.setdefault(region_id, [])
        exact_label = _clean_label(entity.label or entity.semantic_role or "").lower()
        desc_label = _clean_label(str(entity.attributes.get("description") or entity.attributes.get("AXDescription") or "")).lower()
        hinted = list(dict.fromkeys(label_hints.get(exact_label, []) + label_hints.get(desc_label, [])))
        hinted = [
            ctype
            for ctype in hinted
            if (
                region_kind is None
                or not (label_regions.get(exact_label, []) or label_regions.get(desc_label, []))
                or (
                    region_kind.value.lower()
                    in set(label_regions.get(exact_label, []) + label_regions.get(desc_label, []))
                )
            )
        ]
        label_types = _label_based_capability_types(entity, region_kind)
        for ctype in list(dict.fromkeys(hinted + label_types)):
            cap_id = f"{ctype}:{eid}:{region_id or 'global'}"
            if cap_id in capability_graph.nodes:
                continue
            cap = Capability(
                capability_id=cap_id,
                type=ctype,
                confidence=0.72 if ctype in {"InitiateVoiceCall", "InitiateVideoCall"} else 0.58,
                provider_entities=[eid],
                provider_regions=region_ids if region_ids else ([region_id] if region_id else []),
                predicted_transition=_capability_predicted_transition(ctype),
                risk=_capability_risk(ctype, region_kind),
                reversibility=_capability_reversible(ctype, region_kind),
                evidence={
                    "label_match": True,
                    "region_kind": None if region_kind is None else region_kind.value,
                    "entity_label": _clean_label(entity.label or entity.semantic_role or ""),
                    "visible": True,
                },
                visible=True,
            )
            capability_graph.nodes[cap_id] = cap
            region_caps[region_id].append(cap_id)
            visible_types[region_id].append(ctype)
            if goal is not None and ctype in goal_capability_types(goal):
                visible_goal_caps.append(cap_id)
        for hyp in hyps:
            ctype = _AFFORDANCE_TO_CAPABILITY.get(hyp.id, _AFFORDANCE_TO_CAPABILITY.get("unknown", "UnknownCapability"))
            if ctype == "UnknownCapability":
                continue
            cap_id = f"{ctype}:{eid}:{region_id or 'global'}"
            if cap_id in capability_graph.nodes:
                continue
            confidence = min(0.99, max(0.05, float(hyp.p) + (0.12 if hyp.id in {"initiate_session", "search"} else 0.0)))
            if region_kind is RegionKind.FLOATING_MENU and ctype in {"InitiateVoiceCall", "InitiateVideoCall", "SelectParticipants"}:
                confidence = min(0.99, confidence + 0.18)
            if region_kind is RegionKind.COMPOSER and ctype in {"ComposeMessage", "SendMessage"}:
                confidence = min(0.99, confidence + 0.15)
            latent = bool((hyp.evidence or {}).get("latent")) or ctype in latent_probe_types
            visible = not latent
            cap = Capability(
                capability_id=cap_id,
                type=ctype,
                confidence=round(confidence, 4),
                provider_entities=[eid],
                provider_regions=region_ids if region_ids else ([region_id] if region_id else []),
                predicted_transition=_capability_predicted_transition(ctype),
                risk=round(_capability_risk(ctype, region_kind), 4),
                reversibility=_capability_reversible(ctype, region_kind),
                evidence={
                    "affordance_id": hyp.id,
                    "region_kind": None if region_kind is None else region_kind.value,
                    "entity_label": _clean_label(entity.label or entity.semantic_role or ""),
                    "visible": visible,
                    "latent": latent,
                },
                visible=visible,
            )
            capability_graph.nodes[cap_id] = cap
            region_caps[region_id].append(cap_id)
            visible_types[region_id].append(ctype)
            if goal is not None and ctype in goal_capability_types(goal):
                visible_goal_caps.append(cap_id)
            if latent:
                capability_graph.frontier.append(
                    FrontierNode(
                        capability_id=cap_id,
                        type=ctype,
                        reason="latent_probe",
                        parent_capability_id="",
                        region_id=region_id,
                        confidence=cap.confidence,
                        risk=cap.risk,
                        depth=0,
                    )
                )

    # Add goal-frontier hypotheses when the desired capability is not directly visible.
    goal_types = goal_hints.get(str(getattr(goal, "kind", "") or ""), []) or (goal_capability_types(goal) if goal is not None else [])
    goal_kind = str(getattr(goal, "kind", "") or "")
    for idx, ctype in enumerate(goal_types):
        visible = [cap for cap in capability_graph.nodes.values() if cap.type == ctype and cap.visible]
        if visible:
            continue
        parent_id = ""
        region_id = ""
        reason = "not_visible"
        parent_type = ""
        if ctype == "InitiateVoiceCall":
            parent_type = "RevealCommunicationOptions"
        elif ctype == "InitiateVideoCall":
            parent_type = "RevealCommunicationOptions"
        elif ctype == "SelectParticipants":
            parent_type = "RevealCommunicationOptions"
        elif ctype in {"SendMessage", "ComposeMessage"}:
            parent_type = "OpenConversation"
        elif ctype in {"OpenConversation"}:
            parent_type = "SearchConversation"
        elif ctype in {"OpenSearch", "SearchConversation"}:
            parent_type = "OpenMenu"

        if parent_type:
            parent = next((cap for cap in capability_graph.nodes.values() if cap.type == parent_type and cap.visible), None)
            if parent is not None:
                parent_id = parent.capability_id
                region_id = parent.provider_regions[0] if parent.provider_regions else ""
                reason = f"parent:{parent_type}"
        frontier_id = f"{ctype}:frontier:{region_id or goal_kind or 'global'}"
        cap = Capability(
            capability_id=frontier_id,
            type=ctype,
            confidence=0.18 if parent_id else 0.08,
            provider_entities=[],
            provider_regions=[region_id] if region_id else [],
            predicted_transition=_capability_predicted_transition(ctype),
            risk=0.25 if ctype in {"InitiateVoiceCall", "InitiateVideoCall"} else 0.12,
            reversibility=_capability_reversible(ctype, None),
            evidence={
                "goal_kind": goal_kind,
                "reason": reason,
                "goal_priority_index": idx,
                "visible": False,
            },
            visible=False,
            parent_capability_id=parent_id,
        )
        capability_graph.nodes[frontier_id] = cap
        capability_graph.frontier.append(
            FrontierNode(
                capability_id=frontier_id,
                type=ctype,
                reason=reason,
                parent_capability_id=parent_id,
                region_id=region_id,
                confidence=cap.confidence,
                risk=cap.risk,
                depth=1 if parent_id else 0,
            )
        )
        if parent_id:
            capability_graph.edges.append(
                CapabilityEdge(
                    source_id=parent_id,
                    target_id=frontier_id,
                    kind="enables",
                    confidence=0.7,
                )
            )

    goal_anchor = _goal_node_id(goal or goal_kind or "unknown")
    for cap_id in visible_goal_caps:
        capability_graph.edges.append(
            CapabilityEdge(
                source_id=goal_anchor,
                target_id=cap_id,
                kind="goal_targets",
                confidence=0.9,
            )
        )
    for node in capability_graph.frontier:
        if node.type in goal_types:
            capability_graph.edges.append(
                CapabilityEdge(
                    source_id=goal_anchor,
                    target_id=node.capability_id,
                    kind="goal_targets",
                    confidence=0.4,
                )
            )

    # Visible parent→child dependencies when both are present.
    by_type = {}
    for cap in capability_graph.nodes.values():
        by_type.setdefault(cap.type, []).append(cap)
    if "RevealCommunicationOptions" in by_type:
        for voice_cap in by_type.get("InitiateVoiceCall", []):
            if voice_cap.visible:
                for parent in by_type["RevealCommunicationOptions"]:
                    if parent.visible and parent.capability_id != voice_cap.capability_id:
                        capability_graph.edges.append(
                            CapabilityEdge(
                                source_id=parent.capability_id,
                                target_id=voice_cap.capability_id,
                                kind="enables",
                                confidence=0.55,
                            )
                        )
    if "OpenConversation" in by_type and "SendMessage" in by_type:
        for conv in by_type["OpenConversation"]:
            for msg in by_type["SendMessage"]:
                if conv.visible and msg.visible:
                    capability_graph.edges.append(
                        CapabilityEdge(
                            source_id=conv.capability_id,
                            target_id=msg.capability_id,
                            kind="enables",
                            confidence=0.62,
                        )
                    )

    capability_graph.goal_capability_ids = list(dict.fromkeys(visible_goal_caps))
    return capability_graph


def capability_graph_delta(
    before: Optional[Dict[str, Any]],
    after: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Small diff used by transition evaluation."""

    before_graph = CapabilityGraph.from_dict(before or {}) if before else CapabilityGraph()
    after_graph = CapabilityGraph.from_dict(after or {}) if after else CapabilityGraph()
    before_types = {cap.type for cap in before_graph.nodes.values() if cap.visible}
    after_types = {cap.type for cap in after_graph.nodes.values() if cap.visible}
    before_ids = set(before_graph.nodes)
    after_ids = set(after_graph.nodes)
    frontier_before = len(before_graph.frontier)
    frontier_after = len(after_graph.frontier)
    selected_before = before_graph.select_for_goal(before_graph.goal_kind) if before_graph.goal_kind else None
    selected_after = after_graph.select_for_goal(after_graph.goal_kind) if after_graph.goal_kind else None
    return {
        "predicted_transition": None if selected_before is None else selected_before.predicted_transition,
        "observed_transition": None if selected_after is None else selected_after.predicted_transition,
        "new_capabilities": sorted(after_types - before_types),
        "lost_capabilities": sorted(before_types - after_types),
        "frontier_delta": frontier_after - frontier_before,
        "confidence_delta": round(
            (0.0 if selected_after is None else selected_after.confidence)
            - (0.0 if selected_before is None else selected_before.confidence),
            4,
        ),
        "new_capability_ids": sorted(after_ids - before_ids),
        "lost_capability_ids": sorted(before_ids - after_ids),
    }


def grounded_action_for_capability(
    capability: Capability,
    *,
    entities: Sequence[Entity],
    graph: Optional[WorldGraph] = None,
) -> GroundedAction:
    """Resolve a capability to a concrete entity without label search."""

    by_id = {e.id: e for e in entities if e.visible}
    for eid in capability.provider_entities:
        ent = by_id.get(eid)
        if ent is not None and _validate_grounded_entity(capability, ent):
            return GroundedAction(
                capability_id=capability.capability_id,
                capability_type=capability.type,
                entity_id=eid,
                confidence=round(min(0.99, capability.confidence + 0.1), 4),
                reason="provider_entity",
                expected_transition=capability.predicted_transition,
            )

    # Fall back to the strongest visible entity that matches the capability
    # shape when provider_entities are stale or missing. This keeps high-risk
    # actions grounded on the current screen instead of dropping the target.
    if capability.type in {"InitiateVoiceCall", "InitiateVideoCall", "SelectParticipants", "RevealCommunicationOptions"}:
        matches = [
            ent
            for ent in entities
            if ent.visible and _validate_grounded_entity(capability, ent)
        ]
        if matches:
            best = max(
                matches,
                key=lambda ent: (
                    float(ent.confidence or 0.0),
                    1.0 if any(tok in _clean_label(ent.label or ent.semantic_role or "").lower() for tok in ("voice", "video", "call", "participant", "people", "dropdown", "menu")) else 0.0,
                    -len(_clean_label(ent.label or ent.semantic_role or "")),
                ),
            )
            return GroundedAction(
                capability_id=capability.capability_id,
                capability_type=capability.type,
                entity_id=best.id,
                confidence=round(max(0.25, capability.confidence - 0.02), 4),
                reason="visible_match",
                expected_transition=capability.predicted_transition,
            )

    # Ground by region membership if the provider entity is stale.
    if capability.provider_regions and graph is not None:
        wanted_regions = set(capability.provider_regions)
        for ent in entities:
            if not ent.visible:
                continue
            rids = set(region_ids_for_entity(graph, ent.id))
            if rids & wanted_regions and _validate_grounded_entity(capability, ent):
                return GroundedAction(
                    capability_id=capability.capability_id,
                    capability_type=capability.type,
                    entity_id=ent.id,
                    confidence=round(max(0.2, capability.confidence - 0.05), 4),
                    reason="provider_region",
                    expected_transition=capability.predicted_transition,
                )

    return GroundedAction(
        capability_id=capability.capability_id,
        capability_type=capability.type,
        entity_id=None,
        confidence=capability.confidence,
        reason="unresolved",
        expected_transition=capability.predicted_transition,
    )
