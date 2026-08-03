"""Freeze recorded frames into the committed corpus.

    python -m plugin.evals.harvest --frames <recording dir> --out plugin/evals/fixtures

The recording directory is hundreds of megabytes of PNGs and is not committed.
What lands here is the packet, the reply and the AX-derived shadow state, which
is what the offline metrics read. Re-running with the same recording is
idempotent: fixture ids come from the frame index, not from the harvest order.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from plugin.evals.annotations import annotate, annotation_coverage
from plugin.evals.corpus import (
    DEFAULT_CORPUS_DIR,
    DEFAULT_RECORD_DIR,
    coverage_report,
    fixture_from_frame,
    load_frames,
    select_frames,
    write_fixture,
)


def harvest(
    frames_dir: str = DEFAULT_RECORD_DIR,
    out_dir: str = DEFAULT_CORPUS_DIR,
    *,
    per_bucket: int = 8,
    per_trait: int = 3,
    run: str = "",
) -> Dict[str, Any]:
    frames = load_frames(frames_dir)
    if not frames:
        return {"error": f"no frames found in {frames_dir}", "written": 0}
    picked = select_frames(frames, per_bucket=per_bucket, per_trait=per_trait)
    fixtures = [fixture_from_frame(frame, run=run or Path(frames_dir).name) for frame in picked]
    annotated = annotate(fixtures)
    written: List[str] = []
    for fixture in annotated:
        write_fixture(out_dir, fixture)
        written.append(fixture.id)
    report = {
        "frames_seen": len(frames),
        "written": len(written),
        "out_dir": out_dir,
        "coverage": coverage_report(annotated),
        "annotation_coverage": annotation_coverage(annotated),
        "ids": written,
    }
    index = Path(out_dir) / "_index.json"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze recorded perceptor frames into the eval corpus")
    parser.add_argument("--frames", default=DEFAULT_RECORD_DIR)
    parser.add_argument("--out", default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--per-bucket", type=int, default=8)
    parser.add_argument("--per-trait", type=int, default=3)
    parser.add_argument("--run", default="")
    args = parser.parse_args(argv)

    report = harvest(
        args.frames,
        args.out,
        per_bucket=args.per_bucket,
        per_trait=args.per_trait,
        run=args.run,
    )
    if report.get("error"):
        print(report["error"])
        return 1
    coverage = report["coverage"]
    print(f"harvested {report['written']} fixtures from {report['frames_seen']} frames -> {report['out_dir']}")
    print(f"  phases: {coverage['phases']}")
    print(f"  traits: {coverage['traits']}")
    if coverage["missing_failure_traits"]:
        print(f"  missing failure traits: {coverage['missing_failure_traits']}")
    print(f"  annotation coverage: {report['annotation_coverage']['rates']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
