"""CLI: python -m plugin.evals.perception_semantic [--json]"""

from __future__ import annotations

import argparse
import json
import sys

from plugin.evals.perception_semantic.metamorphic import expand_family
from plugin.evals.perception_semantic.projector import assert_production_projector
from plugin.evals.perception_semantic.schema import load_cases
from plugin.evals.perception_semantic.score import score_corpus, score_case


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Semantic perception golden harness")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--expand-metamorphic", action="store_true")
    args = parser.parse_args(argv)

    cases = load_cases()
    if args.expand_metamorphic:
        expanded = []
        for c in cases:
            if c.metamorphic_of:
                expanded.append(c)
            else:
                expanded.extend(expand_family(c))
        cases = expanded

    report = score_corpus(cases)
    projector_ok = True
    projector_details = []
    for c in cases:
        if c.metamorphic_of and not c.packet:
            continue
        pr = assert_production_projector(c)
        projector_details.append({"id": c.id, **pr})
        projector_ok = projector_ok and bool(pr.get("ok"))

    report["production_projector_ok"] = projector_ok
    report["projector"] = projector_details
    # Gate: zero contamination on annotated/scrubbed.
    contam = float(report.get("cross_surface_contamination_rate") or 0.0)
    report["gate_zero_contamination"] = contam == 0.0
    report["all_passed"] = (
        report["failed"] == 0 and report["gate_zero_contamination"] and projector_ok
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"semantic_perception cases={report['cases']} scores={report['scores']} "
            f"passed={report['passed']} failed={report['failed']} "
            f"contamination={contam:.3f} projector_ok={projector_ok}"
        )
        for layer, acc in sorted((report.get("layer_accuracy") or {}).items()):
            print(f"  layer {layer}: {acc:.1%}")
        if not report["all_passed"]:
            for d in report.get("details") or []:
                if not d.get("passed"):
                    print("FAIL", d.get("case_id"))
                    for c in d.get("checks") or []:
                        if not c.get("passed"):
                            print("  ", c.get("layer"), c.get("detail"))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
