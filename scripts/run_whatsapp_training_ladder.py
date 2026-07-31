#!/usr/bin/env python3
"""Run the WhatsApp training ladder one test at a time and stop on first fail."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTEST = ROOT / ".venv" / "bin" / "pytest"

TESTS = [
    "tests/plugin/test_whatsapp_training_ladder.py::test_stage_01_header_is_open_chat_not_info_card_chrome",
    "tests/plugin/test_whatsapp_training_ladder.py::test_stage_02_timeline_message_beats_profile_panel_actions",
    "tests/plugin/test_whatsapp_training_ladder.py::test_stage_03_source_binding_survives_overlay_and_backtracks_generic_surface",
    "tests/plugin/test_whatsapp_training_ladder.py::test_stage_04_destination_picker_only_on_picker_surface",
    "tests/plugin/test_whatsapp_training_ladder.py::test_stage_05_irreversible_threshold_is_configurable",
    "tests/plugin/test_whatsapp_training_ladder.py::test_stage_06_high_risk_selector_uses_dedicated_task_and_risk_gate_for_forward_picker",
    "tests/plugin/test_whatsapp_training_ladder.py::test_stage_07_high_risk_selector_surfaces_forward_risk_and_goal_context",
    "tests/plugin/test_whatsapp_training_ladder.py::test_stage_08_google_maps_share_link_prompt_prefers_timeline_link_over_profile_chrome",
    "tests/plugin/test_whatsapp_training_ladder.py::test_stage_09_google_maps_location_share_prompt_prefers_timeline_link_over_profile_chrome",
]


def main() -> int:
    if not PYTEST.exists():
        print(f"pytest not found at {PYTEST}", file=sys.stderr)
        return 1

    for test in TESTS:
        print(f"\n=== RUN {test} ===", flush=True)
        proc = subprocess.run([str(PYTEST), "-q", test], cwd=ROOT)
        if proc.returncode != 0:
            print(f"=== STOPPED AT {test} (exit {proc.returncode}) ===", flush=True)
            return proc.returncode
    print("\n=== ALL WHATSAPP TRAINING CASES PASSED ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
