"""Perceptual continuity: is what the agent looked at still there when it acts?

Perception photographs the screen, the models deliberate for the better part of a
minute, and only then does the action land. This submodule spans that gap.

:mod:`witness` provides the cheap live reads — window-server facts about the
surface, and an OCR read-back of the target rectangle. :mod:`relevance` turns
those into a verdict on one question: did what changed intervene in the work, or
merely happen nearby?

The judgement is an *expectation check*, not a before/after diff. Since the
"before" picture is already ~60s old by the time it would be compared, diffing
two stale stamps proves nothing; the live rectangle is instead checked against
what the decision meant to act on.
"""

from plugin.perception.continuity.relevance import (
    CONFIRMED,
    FOCUS_DISTURBED,
    INDETERMINATE,
    SURFACE_LOST,
    ContinuityVerdict,
    assess_continuity,
    continuity_check_enabled,
    guard_click,
    verify_before_acting,
)
from plugin.perception.continuity.witness import (
    ReadBack,
    Surface,
    TargetExpectation,
    capture_rect,
    dhash,
    expectation_from,
    frontmost_app_name,
    hamming,
    label_present,
    norm_app,
    norm_text,
    ocr_image,
    read_back,
    significant_tokens,
    take_surface,
    window_snapshot,
)

__all__ = [
    "CONFIRMED",
    "ContinuityVerdict",
    "FOCUS_DISTURBED",
    "INDETERMINATE",
    "ReadBack",
    "SURFACE_LOST",
    "Surface",
    "TargetExpectation",
    "assess_continuity",
    "capture_rect",
    "continuity_check_enabled",
    "dhash",
    "guard_click",
    "expectation_from",
    "frontmost_app_name",
    "hamming",
    "label_present",
    "norm_app",
    "norm_text",
    "ocr_image",
    "read_back",
    "significant_tokens",
    "take_surface",
    "verify_before_acting",
    "window_snapshot",
]
