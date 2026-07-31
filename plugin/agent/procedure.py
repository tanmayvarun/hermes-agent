"""Procedure primitive — prompt → best-fit declarative execution substrate.

Procedures are generic, JSON-backed trajectory templates. They do not encode
app-specific click scripts; instead, they describe the intended progression of
subgoals, the bindings that should exist, and the rough recovery shape. Leaf
overlays may still contribute local surface semantics, but the selection and
ordering of the procedure itself stays in the core.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass
    return str(value)


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@dataclass
class ProcedureStage:
    id: str
    objective: str
    required_predicates: List[str] = field(default_factory=list)
    preferred_capabilities: List[str] = field(default_factory=list)
    recovery: List[str] = field(default_factory=list)
    reversible: bool = True
    confidence_threshold: float = 0.0
    notes: str = ""

    def render(self, bindings: Dict[str, Any]) -> Dict[str, Any]:
        rendered_bindings = {str(k): _json_safe(v) for k, v in bindings.items()}
        objective = self.objective.format_map(_SafeFormatDict(rendered_bindings))
        return {
            "id": self.id,
            "objective": objective,
            "required_predicates": list(self.required_predicates),
            "preferred_capabilities": list(self.preferred_capabilities),
            "recovery": list(self.recovery),
            "reversible": bool(self.reversible),
            "confidence_threshold": round(float(self.confidence_threshold or 0.0), 4),
            "notes": self.notes,
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcedureStage":
        return cls(
            id=str(data.get("id") or ""),
            objective=str(data.get("objective") or ""),
            required_predicates=[str(x) for x in (data.get("required_predicates") or [])],
            preferred_capabilities=[str(x) for x in (data.get("preferred_capabilities") or [])],
            recovery=[str(x) for x in (data.get("recovery") or [])],
            reversible=bool(data.get("reversible", True)),
            confidence_threshold=float(data.get("confidence_threshold") or 0.0),
            notes=str(data.get("notes") or ""),
        )


@dataclass
class ProcedureDefinition:
    id: str
    title: str
    app: str = ""
    summary: str = ""
    goal_kinds: List[str] = field(default_factory=list)
    family_keys: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    stages: List[ProcedureStage] = field(default_factory=list)
    confidence_threshold: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def bindings_for_goal(self, goal: Any) -> Dict[str, Any]:
        return {
            "app": getattr(goal, "app", "") or self.app,
            "kind": getattr(goal, "kind", ""),
            "contact": getattr(goal, "contact", ""),
            "target_contact": getattr(goal, "target_contact", ""),
            "link_query": getattr(goal, "link_query", ""),
            "prompt": getattr(goal, "prompt", ""),
            "description": getattr(goal, "description", ""),
            "family_key": getattr(goal, "family_key", lambda: "")(),
            "signature_key": getattr(goal, "signature_key", lambda: "")(),
        }

    def stage_objectives(self, goal: Any) -> List[str]:
        bindings = self.bindings_for_goal(goal)
        out: List[str] = []
        for stage in self.stages:
            rendered = _render_stage(stage, bindings)
            objective = str(rendered.get("objective") or "").strip()
            if objective:
                out.append(objective)
        return out

    def stage_progress(self, goal: Any, features: Any) -> Optional["ProcedureStageProgress"]:
        if not self.stages:
            return None
        bindings = self.bindings_for_goal(goal)
        total = len(self.stages)
        completed: List[str] = []
        procedure_ratio = 0.0
        for idx, stage in enumerate(self.stages):
            rendered = _render_stage(stage, bindings)
            required = [str(x).strip() for x in (rendered.get("required_predicates") or []) if str(x).strip()]
            satisfied = [pred for pred in required if _feature_truth(features, pred)]
            missing = [pred for pred in required if pred not in satisfied]
            stage_ratio = 1.0 if not required else len(satisfied) / max(1, len(required))
            if missing:
                procedure_ratio = (len(completed) + stage_ratio) / max(1, total)
                return ProcedureStageProgress(
                    procedure_id=self.id,
                    procedure_title=self.title,
                    stage_index=idx,
                    stage_id=str(rendered.get("id") or stage.id),
                    stage_objective=str(rendered.get("objective") or stage.objective).strip(),
                    required_predicates=required,
                    satisfied_predicates=satisfied,
                    missing_predicates=missing,
                    preferred_capabilities=[str(x) for x in rendered.get("preferred_capabilities") or []],
                    recovery=[str(x) for x in rendered.get("recovery") or []],
                    reversible=bool(rendered.get("reversible", stage.reversible)),
                    confidence_threshold=float(rendered.get("confidence_threshold") or 0.0),
                    complete=False,
                    procedure_complete=False,
                    stage_progress=round(stage_ratio, 4),
                    procedure_progress=round(procedure_ratio, 4),
                    completed_stage_ids=list(completed),
                )
            completed.append(str(rendered.get("id") or stage.id))
            procedure_ratio = (len(completed)) / max(1, total)
        last_stage = self.stages[-1]
        rendered = _render_stage(last_stage, bindings)
        return ProcedureStageProgress(
            procedure_id=self.id,
            procedure_title=self.title,
            stage_index=total - 1,
            stage_id=str(rendered.get("id") or last_stage.id),
            stage_objective=str(rendered.get("objective") or last_stage.objective).strip(),
            required_predicates=[str(x) for x in rendered.get("required_predicates") or []],
            satisfied_predicates=[str(x) for x in rendered.get("required_predicates") or []],
            missing_predicates=[],
            preferred_capabilities=[str(x) for x in rendered.get("preferred_capabilities") or []],
            recovery=[str(x) for x in rendered.get("recovery") or []],
            reversible=bool(rendered.get("reversible", last_stage.reversible)),
            confidence_threshold=float(rendered.get("confidence_threshold") or 0.0),
            complete=True,
            procedure_complete=True,
            stage_progress=1.0,
            procedure_progress=1.0,
            completed_stage_ids=list(completed),
        )

    def current_stage(self, goal: Any, features: Any) -> Optional["ProcedureStageProgress"]:
        return self.stage_progress(goal, features)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "app": self.app,
            "summary": self.summary,
            "goal_kinds": list(self.goal_kinds),
            "family_keys": list(self.family_keys),
            "tags": list(self.tags),
            "keywords": list(self.keywords),
            "stages": [stage.to_dict() for stage in self.stages],
            "confidence_threshold": round(float(self.confidence_threshold or 0.0), 4),
            "metadata": _json_safe(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcedureDefinition":
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            app=str(data.get("app") or ""),
            summary=str(data.get("summary") or ""),
            goal_kinds=[str(x) for x in (data.get("goal_kinds") or [])],
            family_keys=[str(x) for x in (data.get("family_keys") or [])],
            tags=[str(x) for x in (data.get("tags") or [])],
            keywords=[str(x) for x in (data.get("keywords") or [])],
            stages=[
                ProcedureStage.from_dict(stage)
                for stage in (data.get("stages") or [])
                if isinstance(stage, dict)
            ],
            confidence_threshold=float(data.get("confidence_threshold") or 0.0),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ProcedureSelection:
    definition: ProcedureDefinition
    score: float
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "definition": self.definition.to_dict(),
            "score": round(float(self.score or 0.0), 4),
            "reasons": list(self.reasons),
        }


@dataclass
class ProcedureStageProgress:
    procedure_id: str
    procedure_title: str
    stage_index: int
    stage_id: str
    stage_objective: str
    required_predicates: List[str] = field(default_factory=list)
    satisfied_predicates: List[str] = field(default_factory=list)
    missing_predicates: List[str] = field(default_factory=list)
    preferred_capabilities: List[str] = field(default_factory=list)
    recovery: List[str] = field(default_factory=list)
    reversible: bool = True
    confidence_threshold: float = 0.0
    complete: bool = False
    procedure_complete: bool = False
    stage_progress: float = 0.0
    procedure_progress: float = 0.0
    completed_stage_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _normalize_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[\s\-]+", "_", text)
    return text


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return float(value) != 0.0
    if isinstance(value, str):
        low = value.strip().lower()
        return low not in {"", "0", "false", "none", "no", "off"}
    return bool(value)


def _feature_truth(features: Any, predicate: str) -> bool:
    key = _normalize_key(predicate)
    if not key:
        return False

    def _lookup(source: Any, candidate: str) -> tuple[bool, Any]:
        if source is None:
            return False, None
        if isinstance(source, dict):
            if candidate in source:
                return True, source.get(candidate)
        else:
            if hasattr(source, candidate):
                return True, getattr(source, candidate)
        return False, None

    def _check_source(source: Any, candidate: str) -> Optional[bool]:
        found, value = _lookup(source, candidate)
        if found:
            return _truthy(value)
        return None

    candidates = [key, key.replace(".", "_")]
    extras_sources: List[Any] = []
    if isinstance(features, dict):
        extras_sources.append(features)
        extras = features.get("extras")
    else:
        extras_sources.append(features)
        extras = getattr(features, "extras", None)
    if isinstance(extras, dict):
        extras_sources.append(extras)
        forward_task = extras.get("forward_task")
        if isinstance(forward_task, dict):
            extras_sources.append(forward_task)
            preds = forward_task.get("predicates")
            if isinstance(preds, dict):
                extras_sources.append(preds)
        preds = extras.get("predicates")
        if isinstance(preds, dict):
            extras_sources.append(preds)

    for source in extras_sources:
        for candidate in candidates:
            result = _check_source(source, candidate)
            if result is not None:
                return result
    return False


def _render_stage(stage: ProcedureStage, bindings: Dict[str, Any]) -> Dict[str, Any]:
    rendered = stage.render(bindings)
    rendered["required_predicates"] = [str(x) for x in rendered.get("required_predicates") or []]
    rendered["preferred_capabilities"] = [str(x) for x in rendered.get("preferred_capabilities") or []]
    rendered["recovery"] = [str(x) for x in rendered.get("recovery") or []]
    return rendered


def _procedure_package():
    return resources.files("plugin.agent.procedures")


@lru_cache(maxsize=1)
def load_procedure_definitions() -> Tuple[ProcedureDefinition, ...]:
    defs: List[ProcedureDefinition] = []
    try:
        for entry in _procedure_package().iterdir():
            if entry.suffix.lower() != ".json":
                continue
            try:
                payload = json.loads(entry.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                defs.append(ProcedureDefinition.from_dict(payload))
    except Exception:
        return tuple()
    defs.sort(key=lambda proc: proc.id)
    return tuple(defs)


def _goal_text(goal: Any) -> str:
    parts = [
        getattr(goal, "kind", ""),
        getattr(goal, "app", ""),
        getattr(goal, "contact", ""),
        getattr(goal, "target_contact", ""),
        getattr(goal, "link_query", ""),
        getattr(goal, "prompt", ""),
        getattr(goal, "description", ""),
    ]
    return _norm(" ".join(str(p or "") for p in parts))


def _family_key(goal: Any) -> str:
    fn = getattr(goal, "family_key", None)
    if callable(fn):
        try:
            return _norm(fn())
        except Exception:
            pass
    kind = _norm(getattr(goal, "kind", ""))
    if not kind:
        return ""
    if "call" in kind:
        return kind.split("_")[0] + "_call"
    if "message" in kind:
        return kind.split("_")[0] + "_message"
    if "forward" in kind:
        return kind.split("_")[0] + "_forward"
    if "search" in kind:
        return kind.split("_")[0] + "_search"
    return kind


def _token_overlap_score(haystack: str, needles: Sequence[str]) -> float:
    if not haystack:
        return 0.0
    hay = set(re.split(r"[^a-z0-9]+", haystack))
    hay.discard("")
    score = 0.0
    for needle in needles:
        n = _norm(needle)
        if not n:
            continue
        toks = [t for t in re.split(r"[^a-z0-9]+", n) if t]
        if not toks:
            continue
        hits = sum(1 for tok in toks if tok in hay or tok in haystack)
        if hits:
            score += hits / len(toks)
    return score


def score_procedure(goal: Any, procedure: ProcedureDefinition) -> Tuple[float, List[str]]:
    goal_kind = _norm(getattr(goal, "kind", ""))
    app = _norm(getattr(goal, "app", ""))
    text = _goal_text(goal)
    family = _family_key(goal)
    reasons: List[str] = []
    score = 0.0

    proc_kind_set = {_norm(x) for x in procedure.goal_kinds}
    proc_family_set = {_norm(x) for x in procedure.family_keys}
    proc_app = _norm(procedure.app)
    proc_keywords = [_norm(x) for x in procedure.keywords]
    proc_tags = [_norm(x) for x in procedure.tags]
    proc_blob = " ".join([procedure.id, procedure.title, procedure.summary, " ".join(proc_keywords), " ".join(proc_tags)])
    proc_blob = _norm(proc_blob)

    if goal_kind and goal_kind in proc_kind_set:
        score += 5.0
        reasons.append("goal_kind_match")
    elif goal_kind and proc_kind_set:
        # Small penalty for mismatched kinds so the prompt can still win.
        score -= 0.5

    if family and family in proc_family_set:
        score += 2.5
        reasons.append("family_key_match")
    elif family and proc_family_set:
        score -= 0.25

    if app and proc_app and (app == proc_app or proc_app in app or app in proc_app):
        score += 1.75
        reasons.append("app_match")

    keyword_score = _token_overlap_score(text, proc_keywords + proc_tags)
    if keyword_score:
        score += min(2.75, keyword_score)
        reasons.append("prompt_keyword_overlap")

    blob_overlap = _token_overlap_score(text, [proc_blob])
    if blob_overlap:
        score += min(1.25, blob_overlap * 0.6)

    # Procedure-specific soft boosts for the current prompt shape.
    prompt = _norm(getattr(goal, "prompt", ""))
    if prompt and any(term in prompt for term in {"forward", "share", "send"}):
        if any(term in proc_blob for term in {"forward", "share", "send"}):
            score += 0.75
            reasons.append("forward_like_prompt")
    if prompt and any(term in prompt for term in {"call", "ring", "voice", "video"}):
        if any(term in proc_blob for term in {"call", "voice", "video", "ring"}):
            score += 0.75
            reasons.append("call_like_prompt")
    if prompt and any(term in prompt for term in {"message", "link", "chat", "timeline", "read", "inspect"}):
        if any(term in proc_blob for term in {"message", "link", "chat", "timeline", "read", "inspect"}):
            score += 0.5
            reasons.append("message_like_prompt")

    if getattr(goal, "target_contact", "") and "target_contact" in proc_blob:
        score += 0.1
    if getattr(goal, "link_query", "") and any(term in proc_blob for term in {"link", "message", "forward"}):
        score += 0.2

    return score, reasons


def select_best_procedure(goal: Any, *, min_score: float = 2.0) -> Optional[ProcedureSelection]:
    best: Optional[ProcedureSelection] = None
    for procedure in load_procedure_definitions():
        score, reasons = score_procedure(goal, procedure)
        if best is None or score > best.score:
            best = ProcedureSelection(definition=procedure, score=score, reasons=reasons)
    if best is None or float(best.score or 0.0) < float(min_score or 0.0):
        return None
    return best


def current_procedure_stage(goal: Any, features: Any) -> Optional[Dict[str, Any]]:
    proc = getattr(goal, "procedure", None)
    if proc is None:
        try:
            proc = goal.ensure_procedure()
        except Exception:
            proc = None
    if proc is None or not hasattr(proc, "stage_progress"):
        return None
    progress = proc.stage_progress(goal, features)
    if progress is None:
        return None
    return progress.to_dict()
