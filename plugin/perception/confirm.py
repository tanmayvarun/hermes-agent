"""Perception confirm: cheap validity check before actuation.

Distinct from a full stage1 re-perceive. The actor calls this inside its commit
transaction to ask: *is the brain's named rectangle still what we meant?* If not
(user interrupt, notification, call overlay, list scroll), the actor refuses and
returns to the brain; the brain owns recovery via a fresh perceive + decide.

Implementation is the continuity witness (window surface + OCR/label read-back
of the final rectangle) — not multimodal world synthesis.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Sequence

logger = logging.getLogger(__name__)

SKIPPED = "skipped"


@dataclass(frozen=True)
class PerceptionConfirmResult:
    """Outcome of a cheap perception-confirm call.

    ``valid=True`` means the actor may write. ``state=skipped`` means the gate
    did not run (off / ungrounded / error) and we fail open, same as before the
    confirm API existed.
    """

    valid: bool
    state: str = SKIPPED
    reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["evidence"] = dict(self.evidence)
        return out


def confirm_perception(
    app: str,
    label: str,
    bounds: Optional[Sequence[float]],
    *,
    irreversible: bool = False,
    estimated: bool = False,
) -> PerceptionConfirmResult:
    """Confirm the named target is still at ``bounds``. Never re-perceives."""
    try:
        from plugin.perception.continuity import continuity_check_enabled, guard_click

        if not continuity_check_enabled():
            return PerceptionConfirmResult(
                valid=True,
                state=SKIPPED,
                reason="action_guard_disabled",
            )
        verdict = guard_click(
            app,
            label,
            bounds,
            irreversible=irreversible,
            estimated=estimated,
        )
    except Exception as exc:
        logger.debug("perception confirm skipped: %s", exc)
        return PerceptionConfirmResult(
            valid=True,
            state=SKIPPED,
            reason=f"confirm_error:{exc}",
        )

    if verdict is None:
        # Ungrounded or gate declined to check — fail open.
        return PerceptionConfirmResult(
            valid=True,
            state=SKIPPED,
            reason="ungrounded_or_unchecked",
        )

    state = str(getattr(verdict, "state", "") or SKIPPED)
    reason = str(getattr(verdict, "reason", "") or "")
    evidence = dict(getattr(verdict, "evidence", None) or {})
    may_commit = bool(getattr(verdict, "may_commit", True))
    return PerceptionConfirmResult(
        valid=may_commit,
        state=state,
        reason=reason,
        evidence=evidence,
    )
