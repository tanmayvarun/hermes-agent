#!/usr/bin/env python3
"""Capture a screenshot + AX pair for the perceptor eval set.

The existing fixtures under ``plugin/experiments/fixtures`` are AX-only JSON,
which cannot exercise a multimodal perceptor at all. This records what the
agent actually sees -- the same screenshot and accessibility evidence the
model receives at runtime -- so the eval measures the real input path.

Captures land in ``fixtures/perceptor/`` which is gitignored: real screenshots
contain personal conversations and must not be committed.

Usage:
    python -m plugin.experiments.capture_perceptor_fixture --name chat_list \
        --surface chat_list --note "WhatsApp conversation list, no chat open"
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from plugin.perception.observation import Observation  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "perceptor"


def _observe(app: str) -> Observation:
    from plugin.perception.fusion.fuse import observe_fused

    return observe_fused(app, with_screenshot=True)


def _node_payload(node: Any) -> Dict[str, Any]:
    return {
        "role": getattr(node, "role", ""),
        "name": getattr(node, "name", ""),
        "description": getattr(node, "description", ""),
        "value": getattr(node, "value", ""),
        "enabled": bool(getattr(node, "enabled", True)),
        "bbox": list(getattr(node, "bbox", ()) or ()),
        "children": [_node_payload(child) for child in (getattr(node, "children", None) or [])],
    }


def capture(name: str, *, app: str, surface: str, note: str, expect: Dict[str, Any]) -> Path:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    observation = _observe(app)

    screenshot_src = str(getattr(observation, "screenshot_path", "") or "")
    if not screenshot_src or not Path(screenshot_src).exists():
        raise SystemExit("capture failed: no screenshot was produced (is the screen unlocked?)")

    screenshot_dst = FIXTURE_DIR / f"{name}.png"
    shutil.copyfile(screenshot_src, screenshot_dst)

    nodes = [_node_payload(node) for node in (observation.nodes or [])]
    meta = {
        "name": name,
        "app": app,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "window_name": getattr(observation, "window_name", ""),
        "node_count": len(nodes),
        "coverage": getattr(observation, "coverage", None),
        "degraded": bool(getattr(observation, "degraded", False)),
        "screenshot": screenshot_dst.name,
        "note": note,
        # What a correct perceptor should report for this scene.
        "expect": {"surface": surface, **expect},
        "nodes": nodes,
    }
    meta_path = FIXTURE_DIR / f"{name}.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(
        f"captured {name}: nodes={len(nodes)} degraded={meta['degraded']} "
        f"screenshot={screenshot_dst} meta={meta_path}"
    )
    return meta_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="fixture name, e.g. chat_list")
    parser.add_argument("--app", default="WhatsApp")
    parser.add_argument("--surface", required=True, help="expected surface label")
    parser.add_argument("--note", default="", help="human description of the scene")
    parser.add_argument("--open-conversation", default="", help="expected open conversation")
    parser.add_argument(
        "--expect-keyword",
        action="append",
        default=[],
        help="word the summary should mention (repeatable)",
    )
    parser.add_argument("--delay", type=float, default=0.0, help="seconds to wait before capture")
    args = parser.parse_args()

    if args.delay:
        print(f"capturing in {args.delay:.0f}s — arrange the screen now...")
        time.sleep(args.delay)

    capture(
        args.name,
        app=args.app,
        surface=args.surface,
        note=args.note,
        expect={
            "open_conversation": args.open_conversation,
            "summary_keywords": list(args.expect_keyword),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
