"""Generic live observation helpers shared by app-specific experiment runners."""

from __future__ import annotations

import os
import time
from typing import Any, List, Optional

from plugin.experiments.logger import EventLogger
from plugin.perception.observation import Observation
from plugin.perception.sources.base import format_observation_raw_summary
from plugin.perception.macos.accessibility.observer import get_observer, macapptree_available
from plugin.worldmodel.model import WorldModel


def entity_snapshot(wm: WorldModel, limit: int = 40) -> List[dict[str, Any]]:
    """Compact visible-entity snapshot for experiment logs."""
    return [
        {
            "id": e.id,
            "type": e.entity_type,
            "semantic": e.semantic_role,
            "label": e.label,
            "actions": e.actions,
            "snapshots": e.snapshot_count,
        }
        for e in wm.entities.values()
        if e.visible
    ][:limit]


def format_raw_observation_trace(obs: Observation, *, max_nodes: int = 15, max_message_like: int = 8) -> str:
    return format_observation_raw_summary(obs, max_nodes=max_nodes, max_message_like=max_message_like)


def _live_observe(
    log: EventLogger,
    *,
    app: str,
    step: int,
    with_screenshot: bool,
    include_overlays: bool = False,
) -> Observation:
    """Fuse pyobjc_ax + macapptree when possible; prefer deep AX as primary."""
    obs: Optional[Observation] = None
    errors: List[str] = []
    t0 = time.time()
    strict_perception = str(os.getenv("HERMES_FORWARD_STRICT_PERCEPTION", "")).strip().lower() in {"1", "true", "yes", "on"}
    try:
        source_timeout_s = float(os.getenv("HERMES_FORWARD_PERCEPTION_SOURCE_TIMEOUT_SECONDS", "30") or 30)
    except Exception:
        source_timeout_s = 30.0
    try:
        strict_retries = int(os.getenv("HERMES_FORWARD_STRICT_PERCEPTION_RETRIES", "3") or 3)
    except Exception:
        strict_retries = 3
    strict_retries = max(1, strict_retries)
    print(
        f"[observe_begin step={step}] app={app} screenshot={with_screenshot} "
        f"overlays={include_overlays}",
        flush=True,
    )
    log.step(
        "observe_begin",
        step=step,
        message=f"app={app} screenshot={with_screenshot} overlays={include_overlays}",
    )
    try:
        from plugin.perception.fusion.fuse import observe_fused

        def _trace_bundle(source_id: str, bundle: Any) -> None:
            obs_local = getattr(bundle, "observation", None)
            raw_summary = ""
            if obs_local is not None:
                try:
                    raw_summary = format_raw_observation_trace(obs_local, max_nodes=10, max_message_like=6)
                except Exception:
                    raw_summary = ""
            payload = {
                "source_id": source_id,
                "latency_ms": getattr(bundle, "latency_ms", None),
                "coverage_self": getattr(bundle, "coverage_self", None),
                "degraded": getattr(bundle, "degraded", None),
                "raw_meta": getattr(bundle, "raw_meta", {}) or {},
                "raw_summary": raw_summary,
            }
            print(f"[observation_raw_source step={step} source={source_id}]\n{raw_summary}", flush=True)
            log.log("observation_raw_source", payload, step=step)

        for attempt in range(1, strict_retries + 1):
            tf = time.time()
            print(f"[observe_try_fused step={step}] prefer_source=pyobjc_ax secondary=True", flush=True)
            log.step(
                "observe_try_fused",
                step=step,
                message="prefer_source=pyobjc_ax secondary=True",
                detail=f"attempt={attempt}/{strict_retries}",
            )
            fused, report = observe_fused(
                app,
                secondary=True,
                prefer_source="pyobjc_ax",
                source_timeout_s=source_timeout_s,
                trace_bundle=_trace_bundle,
                with_screenshot=with_screenshot,
                include_overlays=include_overlays,
            )
            if len(fused.nodes) > 0:
                obs = fused
                print(f"[observe_done_fused step={step}] nodes={len(fused.nodes)} elapsed={time.time() - tf:.2f}s", flush=True)
                log.step(
                    "observe_fused",
                    step=step,
                    message=f"sources={report.sources} agreement={report.agreement}",
                    detail=f"{report.node_counts} elapsed={time.time() - tf:.2f}s attempt={attempt}/{strict_retries}",
                )
                break
            errors.append("fused returned 0 nodes")
            log.step(
                "observe_fused_empty",
                step=step,
                status="fail",
                message=f"empty fused observe attempt={attempt}/{strict_retries}",
                detail=f"elapsed={time.time() - tf:.2f}s",
            )
            if attempt < strict_retries:
                _wait(log, 1.0, reason="retry after empty fused observe", step=step)
        if obs is None and strict_perception:
            raise RuntimeError("strict perception required fused observation with nodes > 0")
    except Exception as e:
        errors.append(f"fuse: {e}")
        if strict_perception:
            raise RuntimeError("strict perception required fused observation") from e
        obs = None

    if obs is None and not strict_perception:
        try:
            from plugin.perception.macos.accessibility.ax_tree import observe_app_ax

            ta = time.time()
            print(f"[observe_try_pyobjc step={step}] fallback=pyobjc_ax", flush=True)
            log.step("observe_try_pyobjc", step=step, message="fallback=pyobjc_ax")
            obs = observe_app_ax(app)
            if len(obs.nodes) == 0:
                errors.append("pyobjc returned 0 nodes")
                obs = None
                print(f"[observe_pyobjc_empty step={step}] elapsed={time.time() - ta:.2f}s", flush=True)
                log.step("observe_pyobjc_empty", step=step, status="fail", message=f"elapsed={time.time() - ta:.2f}s")
            else:
                print(f"[observe_done_pyobjc step={step}] nodes={len(obs.nodes)} elapsed={time.time() - ta:.2f}s", flush=True)
                log.step("observe_pyobjc", step=step, message=f"nodes={len(obs.nodes)} elapsed={time.time() - ta:.2f}s")
        except Exception as e:
            errors.append(f"pyobjc: {e}")
            obs = None

    if obs is None and not strict_perception and macapptree_available():
        try:
            tm = time.time()
            print(f"[observe_try_macapptree step={step}] with_screenshot={with_screenshot}", flush=True)
            log.step("observe_try_macapptree", step=step, message=f"with_screenshot={with_screenshot}")
            observer = get_observer(prefer="macapptree", with_screenshot=with_screenshot)
            obs = observer.observe(app)
            if len(obs.nodes) == 0:
                errors.append("macapptree returned 0 nodes")
                obs = None
                print(f"[observe_macapptree_empty step={step}] elapsed={time.time() - tm:.2f}s", flush=True)
                log.step("observe_macapptree_empty", step=step, status="fail", message=f"elapsed={time.time() - tm:.2f}s")
            else:
                print(f"[observe_done_macapptree step={step}] nodes={len(obs.nodes)} elapsed={time.time() - tm:.2f}s", flush=True)
                log.step(
                    "observe_fallback_macapptree",
                    step=step,
                    status="warn",
                    message=f"{'; '.join(errors) or 'using macapptree'} elapsed={time.time() - tm:.2f}s",
                )
        except Exception as e:
            errors.append(f"macapptree: {e}")
            obs = None

    if obs is None:
        raise RuntimeError("live observe failed: " + ("; ".join(errors) or "no AX backend"))

    log.observation(
        {
            "app": obs.app_name,
            "window": obs.window_name,
            "nodes": len(obs.nodes),
            "source": obs.source,
            "coverage": obs.coverage,
            "degraded": obs.degraded,
            "screenshot": obs.screenshot_path,
            "sample_labels": [
                (n.name or n.description or "")[:60]
                for n in obs.nodes
                if (n.name or n.description)
            ][:25],
            "fallback_errors": errors or None,
            "elapsed_s": round(time.time() - t0, 3),
        },
        step=step,
        status="ok" if len(obs.nodes) > 0 else "fail",
    )
    trace = format_raw_observation_trace(obs)
    print(f"[observation_raw step={step}]\n{trace}", flush=True)
    log.log(
        "observation_raw",
        {
            "app": obs.app_name,
            "window": obs.window_name,
            "source": obs.source,
            "nodes": len(obs.nodes),
            "coverage": obs.coverage,
            "degraded": obs.degraded,
            "screenshot": obs.screenshot_path,
            "message_like": [
                (n.name or n.description or "")[:180]
                for n in obs.nodes
                if (n.name or n.description or "")
                and any(
                    token in (n.name or n.description or "").lower()
                    for token in ("message", "sent to", "received from", "link", "your message", "reply", "composer")
                )
            ][:8],
            "raw_trace": trace,
        },
        step=step,
    )
    print(f"[observe_complete step={step}] nodes={len(obs.nodes)} elapsed={time.time() - t0:.2f}s", flush=True)
    return obs


def _wait(log: EventLogger, seconds: float, *, reason: str, step: int) -> None:
    log.step("wait", step=step, message=reason, detail=f"{seconds}s")
    time.sleep(seconds)


def _accessibility_trusted() -> bool:
    try:
        from ApplicationServices import AXIsProcessTrusted  # type: ignore

        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def _prompt_accessibility_if_needed() -> bool:
    """Ask macOS to show the Accessibility prompt for *this* host app."""
    try:
        from ApplicationServices import (  # type: ignore
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )
        from Cocoa import NSDictionary  # type: ignore

        opts = NSDictionary.dictionaryWithObject_forKey_(True, kAXTrustedCheckOptionPrompt)
        return bool(AXIsProcessTrustedWithOptions(opts))
    except Exception:
        return _accessibility_trusted()
