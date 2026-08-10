"""Storage environment interpreter → Warning / BlockingCondition.

Deterministic phrasing is a *corroborator/fallback*, not the long-term
primary intelligence. Perception/world semantics should eventually propose
blockers; this module extracts quantified asks and dialog surfaces as evidence.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from plugin.agent.executive.blocking import (
    BlockerLifecycle,
    BlockingCondition,
    EffectPredicate,
    IntentionRef,
    Warning,
)

_STORAGE_CANNOT_CONTINUE = re.compile(
    r"(storage is too full|free up at least|to keep using .{0,40}free up|"
    r"insufficient storage|not enough storage|disk (is )?full)",
    re.I,
)
_STORAGE_MB_ASK = re.compile(
    r"free up at least\s+([0-9]+(?:\.[0-9]+)?)\s*(mb|gb|mib|gib)",
    re.I,
)
_STORAGE_WEAK_WARNING = re.compile(
    r"(storage almost full|low (on )?storage|running out of space|"
    r"disk space is low|storage getting full)",
    re.I,
)


def _bytes_from_ask(amount: float, unit: str) -> int:
    u = unit.lower()
    if u in {"gb", "gib"}:
        return int(amount * (1024**3))
    return int(amount * (1024**2))


def detect_storage_signals(
    *,
    observation_texts: Sequence[str] = (),
    view: Optional[Dict[str, Any]] = None,
    features: Optional[Dict[str, Any]] = None,
    intention_id: str = "",
    app: str = "",
) -> Tuple[List[Warning], List[BlockingCondition]]:
    """Evidence-weighted storage warning vs progress blocker."""
    view = view if isinstance(view, dict) else {}
    extras: Dict[str, Any] = {}
    if features is not None:
        if hasattr(features, "extras") and isinstance(features.extras, dict):
            extras = dict(features.extras)
        elif isinstance(features, dict):
            extras = dict(features.get("extras") or features)

    texts: List[str] = []
    for t in observation_texts or []:
        if str(t).strip():
            texts.append(str(t).strip())
    for w in extras.get("system_warnings") or view.get("system_warnings") or []:
        if str(w).strip():
            texts.append(str(w).strip())
    for d in extras.get("dialogs") or view.get("dialogs") or []:
        if str(d).strip():
            texts.append(str(d).strip())
    blob = "\n".join(texts)

    warnings: List[Warning] = []
    blockers: List[BlockingCondition] = []

    screen = str(
        extras.get("screen_kind") or view.get("screen") or extras.get("wa_screen") or ""
    ).strip().lower()
    dialog_like = screen in {"dialog", "modal"} or bool(extras.get("has_dialog"))
    storage_pressure_flag = bool(
        extras.get("storage_pressure") or view.get("storage_pressure")
    )
    # Observed inability to progress (failed forward / blocked phase) is
    # first-class evidence — stronger than wording alone.
    progress_failed = bool(
        extras.get("progress_blocked")
        or view.get("progress_blocked")
        or str((view.get("progress") or {}).get("phase") or "").lower() == "blocked"
        or any(
            "blocked" in str(b.get("predicate") or "").lower()
            for b in (view.get("beliefs") or [])
            if isinstance(b, dict)
        )
    )

    strong = bool(_STORAGE_CANNOT_CONTINUE.search(blob))
    weak = bool(_STORAGE_WEAK_WARNING.search(blob)) and not strong
    mb = _STORAGE_MB_ASK.search(blob)
    required_bytes: Optional[int] = None
    if mb:
        try:
            required_bytes = _bytes_from_ask(float(mb.group(1)), mb.group(2))
        except (TypeError, ValueError):
            required_bytes = None

    # Multi-signal score (not a single regex → blocker switch).
    score = 0.0
    if strong:
        score += 0.4
    if dialog_like:
        score += 0.3
    if required_bytes is not None:
        score += 0.2
    if progress_failed:
        score += 0.2
    if storage_pressure_flag and (strong or dialog_like):
        score += 0.1
    if weak and not strong:
        score -= 0.4
    app_op = extras.get("app_operational")
    if app_op is None:
        app_op = view.get("app_operational")
    if app_op is True and not dialog_like:
        score -= 0.7

    is_progress_blocker = score >= 0.75 and strong and (
        dialog_like or required_bytes is not None or progress_failed or storage_pressure_flag
    )

    if weak and not is_progress_blocker:
        warnings.append(
            Warning(
                kind="low_storage",
                severity="warn",
                evidence=[t for t in texts if _STORAGE_WEAK_WARNING.search(t)][:4]
                or texts[:2],
            )
        )

    if is_progress_blocker:
        effect = EffectPredicate(
            subject="storage",
            relation="available_bytes_at_least",
            value=int(required_bytes or 0),
        )
        conf = min(1.0, score)
        suggested = ""
        if "system settings" in blob.lower():
            suggested = "system_settings_storage"
        blocks = [IntentionRef(intention_id=intention_id)] if intention_id else []
        blockers.append(
            BlockingCondition(
                kind="insufficient_storage",
                required_effect=effect,
                blocks=blocks,
                evidence=texts[:6],
                provenance={
                    "surface_ownership": str(
                        app or extras.get("app") or view.get("app") or ""
                    ),
                    "modality": "blocking_dialog" if dialog_like else "warning_text",
                    "confidence": conf,
                    "language_cannot_continue": strong,
                    "quantified_ask_bytes": required_bytes,
                    "progress_failed": progress_failed,
                    "evidence_score": score,
                    "detector": "storage",
                },
                suggested_method_from_environment=suggested,
                lifecycle=BlockerLifecycle.CONFIRMED.value
                if conf >= 0.75
                else BlockerLifecycle.DETECTED.value,
            )
        )
        blockers.append(
            BlockingCondition(
                kind="app_not_operational",
                required_effect=EffectPredicate(
                    subject="app_operational",
                    relation="is_true",
                    value=True,
                ),
                blocks=list(blocks),
                evidence=texts[:4],
                provenance={
                    "modality": "blocking_dialog" if dialog_like else "warning_text",
                    "confidence": conf,
                    "paired_with": "insufficient_storage",
                    "detector": "storage",
                },
                lifecycle=BlockerLifecycle.DETECTED.value,
            )
        )
    elif strong and not dialog_like and required_bytes is None:
        warnings.append(
            Warning(kind="low_storage", severity="warn", evidence=texts[:3])
        )

    return warnings, blockers
