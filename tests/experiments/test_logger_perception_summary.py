from __future__ import annotations

from io import StringIO

from plugin.experiments.logger import EventLogger


def test_perception_summary_prints_block_with_separators(tmp_path):
    console = StringIO()
    log = EventLogger(tmp_path / "run.jsonl", also_console=True, console=console, run_id="run-x")

    log.log(
        "perception_summary",
        {
            "message": "Perception summary[screen_understanding]: screen=conversation",
            "detail": "Perception summary[screen_understanding]: screen=conversation",
            "text": "Perception summary[screen_understanding]: screen=conversation",
        },
    )

    output = console.getvalue()
    assert "perception_summary" in output
    assert "PERCEPTION SUMMARY" in output
    assert "Perception summary[screen_understanding]: screen=conversation" in output
    assert output.count("=") >= 10
    assert output.count("-") >= 10


def test_regular_events_still_print_one_line(tmp_path):
    console = StringIO()
    log = EventLogger(tmp_path / "run.jsonl", also_console=True, console=console, run_id="run-x")

    log.log("step", {"message": "hello", "detail": "world"})

    output = console.getvalue().strip().splitlines()
    assert len(output) == 1
    assert "step" in output[0]
    assert "hello" in output[0]
