"""Fuse multiple ObservationBundles — evidence/hypothesis engine + compat API."""

from __future__ import annotations

import concurrent.futures
import logging
import time
from typing import List, Optional, Tuple

from plugin.perception.fusion.engine import FusionEngine, FusionReport, FusedFrame, get_fusion_engine
from plugin.perception.observation import Observation
from plugin.perception.sources.base import ObservationBundle

logger = logging.getLogger(__name__)

# Re-export for callers / tests
__all__ = [
    "FusionReport",
    "FusedFrame",
    "fuse_observations",
    "observe_fused",
    "observe_fused_frame",
]


def fuse_observations(
    bundles: List[ObservationBundle],
    *,
    app: str = "",
    prefer_source: str = "pyobjc_ax",
) -> Tuple[Observation, FusionReport]:
    """Compat: return projected Observation + FusionReport (belief-based)."""
    _ = prefer_source  # primary selection replaced by property fusion
    frame = get_fusion_engine().fuse_bundles(bundles, app=app)
    return frame.to_observation(), frame.report


def observe_fused_frame(
    app: str,
    *,
    sources: Optional[List] = None,
    secondary: bool = True,
    source_timeout_s: float = 8.0,
    trace_bundle=None,
    with_screenshot: bool = True,
    with_vision: bool = False,
) -> FusedFrame:
    from plugin.perception.sources import default_sources
    from plugin.perception.observation import Observation

    srcs = sources or default_sources(with_screenshot=with_screenshot, with_vision=with_vision)
    if not secondary and srcs:
        srcs = srcs[:1]
    bundles: List[ObservationBundle] = []
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(srcs)))
    try:
        futures = {}
        for s in srcs:
            sid = getattr(s, "source_id", "unknown")
            logger.info("observe_fused_frame: source=%s start app=%s", sid, app)
            futures[pool.submit(s.observe, app)] = sid

        for fut, sid in futures.items():
            try:
                bundle = fut.result(timeout=source_timeout_s)
                bundles.append(bundle)
                logger.info("observe_fused_frame: source=%s done app=%s", sid, app)
                if trace_bundle is not None:
                    try:
                        trace_bundle(sid, bundle)
                    except Exception:
                        logger.exception("observe_fused_frame: trace callback failed for source=%s", sid)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "observe_fused_frame: source=%s timed out after %.1fs; continuing with remaining sources",
                    sid,
                    source_timeout_s,
                )
                bundles.append(
                    ObservationBundle(
                        source_id=sid,
                        observation=Observation(
                            timestamp=time.time(),
                            app_name=app,
                            window_name="",
                            nodes=[],
                            source=sid,
                            coverage=0.0,
                            degraded=True,
                            meta={"error": "timeout"},
                        ),
                        degraded=True,
                        coverage_self=0.0,
                        raw_meta={"error": "timeout"},
                    )
                )
                if trace_bundle is not None:
                    try:
                        trace_bundle(sid, bundles[-1])
                    except Exception:
                        logger.exception("observe_fused_frame: trace callback failed for timeout source=%s", sid)
            except Exception as e:
                logger.warning("observe_fused_frame: source=%s failed app=%s err=%s", sid, app, e)
                bundle = ObservationBundle(
                    source_id=sid,
                    observation=Observation(
                        timestamp=time.time(),
                        app_name=app,
                        window_name="",
                        nodes=[],
                        source=sid,
                        coverage=0.0,
                        degraded=True,
                        meta={"error": str(e)},
                    ),
                    degraded=True,
                    coverage_self=0.0,
                    raw_meta={"error": str(e)},
                )
                bundles.append(bundle)
                if trace_bundle is not None:
                    try:
                        trace_bundle(sid, bundle)
                    except Exception:
                        logger.exception("observe_fused_frame: trace callback failed for error source=%s", sid)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return get_fusion_engine().fuse_bundles(bundles, app=app)


def observe_fused(
    app: str,
    *,
    sources: Optional[List] = None,
    secondary: bool = True,
    prefer_source: str = "pyobjc_ax",
    source_timeout_s: float = 8.0,
    trace_bundle=None,
    with_screenshot: bool = True,
    with_vision: bool = False,
) -> Tuple[Observation, FusionReport]:
    _ = prefer_source
    frame = observe_fused_frame(
        app,
        sources=sources,
        secondary=secondary,
        source_timeout_s=source_timeout_s,
        trace_bundle=trace_bundle,
        with_screenshot=with_screenshot,
        with_vision=with_vision,
    )
    return frame.to_observation(), frame.report
