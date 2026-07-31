"""Generic blocking/system-warning signals shared across app overlays and recovery."""

from __future__ import annotations

import re
from typing import Any, Iterable, List

_SYSTEM_WARNING_PATTERNS = (
    r"\bstorage is too full\b",
    r"\bstorage is full\b",
    r"\bstorage full\b",
    r"\btoo full\b",
    r"\bstorage warning\b",
    r"\bdevice storage full\b",
    r"\bout of space\b",
    r"\bno space left on device\b",
    r"\benospc\b",
    r"\bdisk full\b",
    r"\binsufficient storage\b",
    r"\bfree up space\b",
)


def _collect_strings(value: Any, out: List[str]) -> None:
    if value is None:
        return
    if isinstance(value, str):
        text = value.strip()
        if text:
            out.append(text)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_strings(item, out)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_strings(item, out)
        return
    try:
        text = str(value).strip()
    except Exception:
        return
    if text:
        out.append(text)


def detect_system_warning_evidence(*sources: Any) -> List[str]:
    """Return canonical evidence strings for blocking system warnings."""
    candidates: List[str] = []
    for source in sources:
        _collect_strings(source, candidates)

    joined = "\n".join(candidates).lower()
    evidence: List[str] = []
    for pat in _SYSTEM_WARNING_PATTERNS:
        if re.search(pat, joined, re.IGNORECASE):
            evidence.append(pat)
    return evidence


def has_blocking_system_warning(*sources: Any) -> bool:
    return bool(detect_system_warning_evidence(*sources))
