"""Recovery — reusable perception cycle then DecisionEngine snapshot."""

from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from plugin.agent.action import Action
from plugin.agent.decision import DecisionEngine
from plugin.agent.goal import Goal
from plugin.agent.perception_cycle import refresh_perception
from plugin.agent.system_signals import detect_system_warning_evidence
from plugin.agent.runtime.state import RuntimeState
from plugin.perception.observation import Observation
from plugin.worldmodel.model import WorldPatch
from hermes_cli.plugins import get_bundled_plugins_dir


@dataclass
class RecoveryResult:
    recovered: bool
    patch: Optional[WorldPatch]
    new_action: Optional[Action]
    message: str


@dataclass
class StorageCleanupResult:
    triggered: bool
    reason: str
    evidence: list[str]
    analysis: Dict[str, Any]
    disk_cleanup: Dict[str, Any]
    environments_cleaned: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "triggered": self.triggered,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "analysis": dict(self.analysis),
            "disk_cleanup": dict(self.disk_cleanup),
            "environments_cleaned": self.environments_cleaned,
        }

def detect_storage_pressure(
    *,
    view: Optional[Dict[str, Any]] = None,
    features: Optional[Dict[str, Any]] = None,
    observation_texts: Optional[Sequence[str]] = None,
    execution_message: str = "",
) -> list[str]:
    """Return evidence strings suggesting the current app or host is out of space."""
    evidence = detect_system_warning_evidence(
        view or {},
        features or {},
        list(observation_texts) if observation_texts else [],
        execution_message,
    )

    perception = {}
    if isinstance(features, dict):
        perception = features.get("perception_llm") or {}
    if isinstance(perception, dict):
        screen_type = str(perception.get("screen_type") or "").strip().lower()
        active_surface = str(perception.get("active_surface") or "").strip().lower()
        likely_next_family = str(perception.get("likely_next_family") or "").strip().lower()
        supporting = " ".join(
            str(x).strip().lower() for x in (perception.get("supporting_evidence") or [])
        )
        contradictions = " ".join(
            str(x).strip().lower() for x in (perception.get("contradictions") or [])
        )
        llm_text = " ".join(
            part for part in [screen_type, active_surface, likely_next_family, supporting, contradictions] if part
        )
        if screen_type == "dialog" and "storage" in llm_text:
            evidence.append("perception_llm:storage_dialog")
        elif active_surface.startswith("storage") and any(
            kw in llm_text for kw in ("storage", "space", "full")
        ):
            evidence.append("perception_llm:storage_surface")
        elif likely_next_family == "dismiss" and any(
            kw in llm_text for kw in ("storage", "space", "full")
        ):
            evidence.append("perception_llm:dismiss_storage")
    return evidence


def maybe_cleanup_for_storage_pressure(
    runtime: RuntimeState,
    *,
    view: Optional[Dict[str, Any]] = None,
    features: Optional[Dict[str, Any]] = None,
    observation_texts: Optional[Sequence[str]] = None,
    execution_message: str = "",
    reason_hint: str = "",
) -> Optional[StorageCleanupResult]:
    """Trigger the bundled cleanup routine once per distinct pressure signal."""
    evidence = detect_storage_pressure(
        view=view,
        features=features,
        observation_texts=observation_texts,
        execution_message=execution_message,
    )
    if not evidence:
        return None

    view_sig = ""
    if isinstance(view, dict):
        view_sig = "|".join(
            [
                str(view.get("screen") or ""),
                str(view.get("open_conversation") or ""),
                str(view.get("search_query") or ""),
            ]
        )
    sig = "||".join(sorted(set(evidence))) + f"||{view_sig}||{reason_hint}"
    state = runtime.execution_state
    if getattr(state, "storage_cleanup_signature", "") == sig:
        return None
    state.storage_cleanup_signature = sig
    state.storage_cleanup_count = int(getattr(state, "storage_cleanup_count", 0) or 0) + 1
    analysis = _analyze_storage_cleanup_targets(
        reason=reason_hint or "storage pressure detected",
        evidence=evidence,
    )
    state.world_exploration_needed = True
    return perform_storage_cleanup(
        reason=reason_hint or "storage pressure detected",
        evidence=evidence,
        analysis=analysis,
    )


def perform_storage_cleanup(
    *,
    reason: str,
    evidence: Sequence[str],
    analysis: Optional[Dict[str, Any]] = None,
) -> StorageCleanupResult:
    """Run the bundled cleanup routines for storage pressure."""
    if analysis is None:
        analysis = _analyze_storage_cleanup_targets(reason=reason, evidence=evidence)
    disk_cleanup_summary: Dict[str, Any] = {}
    envs_cleaned = 0

    try:
        disk_cleanup_lib = _load_disk_cleanup_library()
        disk_cleanup_summary = disk_cleanup_lib.quick()
        if hasattr(disk_cleanup_lib, "quick_host_temp"):
            host_temp_summary = disk_cleanup_lib.quick_host_temp()
            disk_cleanup_summary = _merge_cleanup_summaries(
                disk_cleanup_summary,
                host_temp_summary,
            )
    except Exception as exc:
        disk_cleanup_summary = {"deleted": 0, "empty_dirs": 0, "freed": 0, "errors": [str(exc)]}

    try:
        from tools.terminal_tool import cleanup_all_environments

        envs_cleaned = int(cleanup_all_environments() or 0)
    except Exception:
        envs_cleaned = 0

    return StorageCleanupResult(
        triggered=True,
        reason=reason,
        evidence=list(evidence),
        analysis=dict(analysis),
        disk_cleanup=disk_cleanup_summary,
        environments_cleaned=envs_cleaned,
    )


def _merge_cleanup_summaries(*summaries: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {"deleted": 0, "empty_dirs": 0, "freed": 0, "errors": []}
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        merged["deleted"] += int(summary.get("deleted", 0) or 0)
        merged["empty_dirs"] += int(summary.get("empty_dirs", 0) or 0)
        merged["freed"] += int(summary.get("freed", 0) or 0)
        errors = summary.get("errors") or []
        if isinstance(errors, list):
            merged["errors"].extend(str(err) for err in errors if str(err))
    return merged


def _load_disk_cleanup_library():
    """Load the bundled disk-cleanup library without depending on import order."""
    try:
        return importlib.import_module("hermes_plugins.disk_cleanup.disk_cleanup")
    except Exception:
        plugin_dir = get_bundled_plugins_dir() / "disk-cleanup"
        lib_path = plugin_dir / "disk_cleanup.py"
        spec = importlib.util.spec_from_file_location(
            "hermes_plugins.disk_cleanup.disk_cleanup",
            lib_path,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load bundled disk cleanup library from {lib_path}")
        module = importlib.util.module_from_spec(spec)
        module.__package__ = "hermes_plugins.disk_cleanup"
        import sys

        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


def _analyze_storage_cleanup_targets(*, reason: str, evidence: Sequence[str]) -> Dict[str, Any]:
    try:
        disk_cleanup_lib = _load_disk_cleanup_library()
        if hasattr(disk_cleanup_lib, "analyze_low_risk_cleanup_targets"):
            analysis = disk_cleanup_lib.analyze_low_risk_cleanup_targets(
                reason=reason,
                evidence=list(evidence),
            )
            if hasattr(analysis, "to_dict"):
                return analysis.to_dict()
            if isinstance(analysis, dict):
                return dict(analysis)
    except Exception as exc:
        return {
            "reason": reason,
            "evidence": list(evidence),
            "candidates": [],
            "total_size": 0,
            "total_size_human": "0.0 B",
            "low_risk_count": 0,
            "low_risk_human": "0.0 B",
            "sources": {},
            "notes": [f"analysis_failed: {exc}"],
        }
    return {
        "reason": reason,
        "evidence": list(evidence),
        "candidates": [],
        "total_size": 0,
        "total_size_human": "0.0 B",
        "low_risk_count": 0,
        "low_risk_human": "0.0 B",
        "sources": {},
        "notes": ["analysis unavailable"],
    }


def recover_after_unexpected(
    runtime: RuntimeState,
    obs: Observation,
    *,
    goal: str,
) -> RecoveryResult:
    """Patch world via shared perception cycle and snapshot one DecisionEngine action."""
    goal_obj = Goal(kind="whatsapp_voice_call" if "call" in goal.lower() else "unknown", contact=goal)

    def _obs() -> Observation:
        return obs

    snap = refresh_perception(runtime, goal_obj, observe=_obs, action_label="recover_observe")
    new_action = DecisionEngine(selector_enabled=True).decide(goal_obj, runtime.world_model, runtime.execution_state)
    runtime.execution_state.step = 0
    runtime.execution_state.last_action = "recover_observe"
    patch = snap.patch
    retention = float(getattr(patch, "retention", 0) or 0) if patch else 0.0
    screen = getattr(patch, "screen_label", "") if patch else ""
    wv = getattr(patch, "worldview_score", None) if patch else None
    return RecoveryResult(
        recovered=True,
        patch=patch,
        new_action=new_action,
        message=(
            f"patched world screen={screen} "
            f"retention={retention:.2f} worldview={wv}; "
            f"decision snapshot {1 if new_action else 0} action(s)"
        ),
    )


def entity_missing(runtime: RuntimeState, semantic: str) -> bool:
    return runtime.world_model.find_entity(semantic) is None
