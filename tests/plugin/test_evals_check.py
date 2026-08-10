"""Package eval check is the mvn-test gate for live runs."""

from __future__ import annotations

from plugin.evals.check import run_check


def test_package_check_passes_on_current_corpus():
    assert run_check(quick=True) == 0
