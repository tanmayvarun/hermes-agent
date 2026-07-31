"""Perception bake-off — hypothesis fusion vs WorldViewScore."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from plugin.perception.fusion.engine import get_fusion_engine
from plugin.perception.fusion.fuse import fuse_observations, observe_fused_frame
from plugin.perception.sources.base import ObservationBundle
from plugin.perception.sources.macapptree import MacAppTreeSource
from plugin.perception.sources.pyobjc_ax import PyObjcAxSource
from plugin.worldmodel.model import WorldModel


def run_shadow(app: str = "WhatsApp") -> Dict[str, Any]:
    """Run pyobjc_ax + macapptree through FusionEngine, score beliefs."""
    bundles: List[ObservationBundle] = []
    errors: Dict[str, str] = {}
    for src in (PyObjcAxSource(),):
        try:
            bundles.append(src.observe(app))
        except Exception as e:
            errors[src.source_id] = str(e)
    try:
        bundles.append(MacAppTreeSource(with_screenshot=False).observe(app))
    except Exception as e:
        errors["macapptree"] = str(e)

    frame = get_fusion_engine().fuse_bundles(bundles, app=app)
    obs = frame.to_observation()
    wm = WorldModel()
    patch = wm.ingest_fused_frame(frame)
    multi = sum(1 for e in frame.entities if len(e.sources) >= 2)
    return {
        "app": app,
        "sources": frame.report.sources,
        "node_counts": frame.report.node_counts,
        "hypothesis_counts": frame.report.hypothesis_counts,
        "latencies_ms": frame.report.latencies_ms,
        "agreement": frame.report.agreement,
        "conflicts": len(frame.report.conflicts),
        "multi_source_entities": multi,
        "primary": frame.report.primary_source,
        "fused_nodes": len(obs.nodes),
        "fused_entities": len(frame.entities),
        "mean_confidence": round(frame.mean_confidence(), 4),
        "needs_reobserve": frame.report.needs_reobserve,
        "worldview_score": patch.worldview_score,
        "errors": errors,
        "degraded": obs.degraded,
    }


def run_fixture_shadow(fixture: Path) -> Dict[str, Any]:
    from plugin.perception.macos.accessibility.observer import FixtureObserver

    obs = FixtureObserver(fixture).observe()
    bundle = ObservationBundle(
        source_id="fixture",
        observation=obs,
        coverage_self=float(obs.coverage or 1.0),
    )
    frame = get_fusion_engine().fuse_bundles([bundle], app=obs.app_name or "Fixture")
    fused = frame.to_observation()
    wm = WorldModel()
    patch = wm.ingest_fused_frame(frame)
    return {
        "fixture": str(fixture),
        "agreement": frame.report.agreement,
        "hypothesis_counts": frame.report.hypothesis_counts,
        "fused_nodes": len(fused.nodes),
        "mean_confidence": round(frame.mean_confidence(), 4),
        "worldview_score": patch.worldview_score,
        "needs_reobserve": frame.report.needs_reobserve,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Perception source bake-off / belief WorldViewScore")
    p.add_argument("--app", default="WhatsApp")
    p.add_argument("--live-shadow", action="store_true", help="Observe live dual sources")
    p.add_argument("--fixture", type=str, default="")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if args.fixture:
        result = run_fixture_shadow(Path(args.fixture))
    elif args.live_shadow:
        result = run_shadow(args.app)
    else:
        # default: fixture if present
        fx = Path(__file__).resolve().parent / "fixtures" / "whatsapp_conversation.json"
        result = run_fixture_shadow(fx) if fx.is_file() else run_shadow(args.app)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
