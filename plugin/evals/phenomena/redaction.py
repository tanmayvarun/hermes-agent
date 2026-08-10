"""Privacy / sensitivity gate before promoting harvested real-run packets.

Harvest may stay local with full screenshots/AX. Promotion into the permanent
corpus requires a scan + human approval. Automatic commit of arbitrary personal
sessions is refused.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence

# Lightweight PII / high-sensitivity heuristics — not a substitute for review.
_PHONE = re.compile(r"\b(?:\+?\d[\d\-\s]{8,}\d)\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SENSITIVE_PATH = re.compile(
    r"(Library/Messages|Photos Library|\.ssh/|Cookies|Login Data|Keychain)",
    re.I,
)


def scan_candidate(candidate_dir: Path) -> Dict[str, Any]:
    """Return findings. ``ok_to_promote`` is False when human review is required."""
    candidate_dir = Path(candidate_dir)
    findings: List[Dict[str, str]] = []
    texts: List[str] = []

    for name in (
        "observation_texts.json",
        "ax.json",
        "world_before.json",
        "executive_context.json",
        "model_input.json",
        "model_output.json",
    ):
        path = candidate_dir / name
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append({"kind": "read_error", "detail": f"{name}: {exc}"})
            continue
        texts.append(raw)
        if _EMAIL.search(raw):
            findings.append({"kind": "email", "detail": name})
        if _PHONE.search(raw):
            findings.append({"kind": "phone_like", "detail": name})
        if _SENSITIVE_PATH.search(raw):
            findings.append({"kind": "sensitive_path", "detail": name})

    shot = candidate_dir / "screenshot.png"
    has_screenshot = shot.is_file()
    ann: Dict[str, Any] = {}
    if (candidate_dir / "annotation.json").is_file():
        try:
            ann = json.loads(
                (candidate_dir / "annotation.json").read_text(encoding="utf-8")
            )
        except json.JSONDecodeError:
            ann = {}

    approved = str(ann.get("status") or "") in {"approved", "annotated", "ready", "promoted"}
    privacy_ack = bool(ann.get("privacy_ack") or ann.get("redaction_ack"))

    # Screenshots always require explicit privacy ack for promote.
    if has_screenshot and not privacy_ack:
        findings.append(
            {
                "kind": "screenshot_without_privacy_ack",
                "detail": "set annotation.privacy_ack=true after human review",
            }
        )

    ok = approved and (privacy_ack or not has_screenshot) and not any(
        f["kind"] in {"email", "phone_like", "sensitive_path"} for f in findings
    )
    # Allow promote with findings only when human explicitly overrides.
    if ann.get("privacy_override") is True and approved:
        ok = True

    return {
        "ok_to_promote": ok,
        "has_screenshot": has_screenshot,
        "approved": approved,
        "privacy_ack": privacy_ack,
        "findings": findings,
    }


def require_promote_clearance(
    candidate_dir: Path,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """Raise ValueError when promote should be refused."""
    report = scan_candidate(candidate_dir)
    if force:
        report["forced"] = True
        report["ok_to_promote"] = True
        return report
    if not report["ok_to_promote"]:
        raise ValueError(
            "promote blocked by privacy/redaction gate: "
            + json.dumps(report.get("findings") or [], ensure_ascii=False)[:500]
            + " — set annotation.status=approved and privacy_ack=true "
            "(or privacy_override=true after review)"
        )
    return report
