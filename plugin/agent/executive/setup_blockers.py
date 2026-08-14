"""Detect desktop-app setup states Computer Use cannot fix without the user.

Used to stop the closed loop early and surface WAITING_FOR_USER with a
dynamic message + ``user_setup_blocker`` ui_hints — instead of burning steps
on Welcome / Link Device screens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

DESKTOP_APP_READY_PRECONDITION = "desktop_app_ready"
USER_SETUP_BLOCKER_KIND = "user_setup_blocker"

_WELCOME_RE = re.compile(
    r"welcome to whatsapp|message privately with friends and family",
    re.I,
)
_LINK_DEVICE_RE = re.compile(
    r"link (a )?device|link with phone number|scan (the )?qr|qr code|"
    r"use whatsapp on your (computer|phone|other devices)",
    re.I,
)
_CONTINUE_RE = re.compile(r"\bcontinue\b", re.I)
_CHAT_LIST_HINT_RE = re.compile(
    r"\b(chats?|search|archived|communities|status)\b",
    re.I,
)


@dataclass(frozen=True)
class SetupBlocker:
    id: str
    app: str
    title: str
    body: str
    cta: str = "Reply **done** when ready"
    evidence_texts: tuple[str, ...] = ()

    @property
    def question(self) -> str:
        return f"{self.body} {self.cta}."

    @property
    def ui_hints(self) -> Dict[str, Any]:
        return {
            "kind": USER_SETUP_BLOCKER_KIND,
            "blocker": self.id,
            "app": self.app,
            "title": self.title,
            "body": self.body,
            "cta": self.cta,
        }

    def ask_evidence(self) -> Dict[str, Any]:
        """Evidence bag for GoalResult → closed-loop adapter → AgentRuntime ASK."""
        return {
            "fallback": "ask_prerequisite",
            "ask_precondition": DESKTOP_APP_READY_PRECONDITION,
            "ask_question": self.question,
            "ui_hints": self.ui_hints,
            "setup_blocker": self.id,
            "app": self.app,
            "evidence_texts": list(self.evidence_texts)[:12],
        }


def _collect_texts(
    *,
    observation_texts: Sequence[str] = (),
    view: Optional[Dict[str, Any]] = None,
    features: Any = None,
    observation: Any = None,
) -> List[str]:
    texts: List[str] = []
    for t in observation_texts or []:
        if str(t or "").strip():
            texts.append(str(t).strip())

    view = view if isinstance(view, dict) else {}
    for key in ("dialogs", "system_warnings", "labels", "ocr_lines", "visible_text"):
        for item in view.get(key) or []:
            if isinstance(item, dict):
                for k in ("text", "label", "title", "value"):
                    if str(item.get(k) or "").strip():
                        texts.append(str(item.get(k)).strip())
            elif str(item or "").strip():
                texts.append(str(item).strip())

    extras: Dict[str, Any] = {}
    if features is not None:
        if hasattr(features, "extras") and isinstance(features.extras, dict):
            extras = dict(features.extras)
        elif isinstance(features, dict):
            extras = dict(features.get("extras") or features)

    for bag_key in ("perception_summary", "perception_llm"):
        bag = extras.get(bag_key)
        if not isinstance(bag, dict):
            continue
        for k in ("summary", "scene", "screen_type", "active_surface", "notes"):
            if str(bag.get(k) or "").strip():
                texts.append(str(bag.get(k)).strip())
        for obj in bag.get("objects") or []:
            if isinstance(obj, dict) and str(obj.get("text") or "").strip():
                texts.append(str(obj.get("text")).strip())

    if observation is not None:
        app = str(getattr(observation, "app_name", "") or "").strip()
        if app:
            texts.append(app)
        for node in getattr(observation, "nodes", None) or []:
            for attr in ("label", "title", "value", "role"):
                val = getattr(node, attr, None)
                if val is None and isinstance(node, dict):
                    val = node.get(attr)
                if str(val or "").strip():
                    texts.append(str(val).strip())
        meta = getattr(observation, "meta", None) or {}
        if isinstance(meta, dict):
            for line in meta.get("message_like") or meta.get("ocr_lines") or []:
                if isinstance(line, dict):
                    if str(line.get("text") or "").strip():
                        texts.append(str(line.get("text")).strip())
                elif str(line or "").strip():
                    texts.append(str(line).strip())

    # Dedupe while preserving order.
    seen = set()
    out: List[str] = []
    for t in texts:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def detect_setup_blocker(
    *,
    app: str = "",
    observation_texts: Sequence[str] = (),
    view: Optional[Dict[str, Any]] = None,
    features: Any = None,
    observation: Any = None,
) -> Optional[SetupBlocker]:
    """Return a SetupBlocker when the UI is a setup/login wall CU cannot clear."""
    texts = _collect_texts(
        observation_texts=observation_texts,
        view=view,
        features=features,
        observation=observation,
    )
    blob = "\n".join(texts)
    if not blob.strip():
        return None

    app_name = (
        str(app or "").strip()
        or str(getattr(observation, "app_name", "") or "").strip()
        or (
            str((view or {}).get("app") or (view or {}).get("active_app") or "").strip()
            if isinstance(view, dict)
            else ""
        )
        or "the app"
    )
    # Normalize LTR mark / fancy WhatsApp titles.
    app_norm = app_name.replace("\u200e", "").strip() or "the app"
    looks_whatsapp = "whatsapp" in app_norm.lower() or "whatsapp" in blob.lower()

    chat_list_visible = bool(_CHAT_LIST_HINT_RE.search(blob)) and not (
        _WELCOME_RE.search(blob) or _LINK_DEVICE_RE.search(blob)
    )
    if chat_list_visible:
        return None

    evidence = tuple(texts[:12])

    if looks_whatsapp and _LINK_DEVICE_RE.search(blob):
        return SetupBlocker(
            id="whatsapp_link_device_desktop",
            app="WhatsApp",
            title="WhatsApp needs to be linked on this Mac",
            body=(
                "WhatsApp on this Mac isn’t ready — it’s showing the **Link a device** "
                "screen. Finish linking with your phone in the WhatsApp desktop app"
            ),
            evidence_texts=evidence,
        )

    if looks_whatsapp and _WELCOME_RE.search(blob):
        return SetupBlocker(
            id="whatsapp_welcome",
            app="WhatsApp",
            title="WhatsApp isn’t set up on this Mac yet",
            body=(
                "WhatsApp on this Mac is still on the welcome/setup screen"
                + (" (tap **Continue**, then finish linking)" if _CONTINUE_RE.search(blob) else "")
                + ". Complete setup in the WhatsApp app until you see your chat list"
            ),
            evidence_texts=evidence,
        )

    # Generic: perception explicitly says setup/locked with no actionable chat surface.
    extras: Dict[str, Any] = {}
    if features is not None:
        if hasattr(features, "extras") and isinstance(features.extras, dict):
            extras = dict(features.extras)
        elif isinstance(features, dict):
            extras = dict(features.get("extras") or features)
    summary = extras.get("perception_summary") if isinstance(extras.get("perception_summary"), dict) else {}
    screen_type = str(
        summary.get("screen_type")
        or (extras.get("perception_llm") or {}).get("screen_type")
        or (view or {}).get("screen")
        or ""
    ).lower()
    summary_text = str(summary.get("summary") or summary.get("scene") or "").lower()
    locked = any(
        k in screen_type or k in summary_text
        for k in ("setup", "onboarding", "login", "locked", "link device", "welcome")
    )
    if locked and not chat_list_visible:
        return SetupBlocker(
            id="app_setup_locked",
            app=app_norm,
            title=f"{app_norm} isn’t ready",
            body=(
                f"{app_norm} is in a setup or login state I can’t complete from here. "
                f"Finish that in {app_norm} until the normal UI is available"
            ),
            evidence_texts=evidence,
        )
    return None


def probe_desktop_app_ready(app: str = "WhatsApp") -> tuple[bool, Optional[SetupBlocker]]:
    """Best-effort live AX scrape → (ready, blocker_if_any).

    On failure to observe, returns (True, None) so a user **done** can resume
    and CU will re-detect if still blocked.
    """
    app_name = str(app or "WhatsApp").strip() or "WhatsApp"
    try:
        from AppKit import NSWorkspace
        from ApplicationServices import (
            AXUIElementCopyAttributeValue,
            AXUIElementCreateApplication,
            kAXChildrenAttribute,
            kAXRoleAttribute,
            kAXTitleAttribute,
            kAXValueAttribute,
        )
    except Exception:
        return True, None

    pid = None
    target = app_name.lower().replace("\u200e", "")
    for a in NSWorkspace.sharedWorkspace().runningApplications():
        name = str(a.localizedName() or "").replace("\u200e", "").strip().lower()
        if name == target or target in name:
            pid = int(a.processIdentifier())
            break
    if pid is None:
        # App not running — still blocked for WhatsApp-style goals.
        blocker = SetupBlocker(
            id="app_not_running",
            app=app_name,
            title=f"{app_name} isn’t open",
            body=f"Open {app_name} on this Mac and finish any setup until the chat list is visible",
        )
        return False, blocker

    root = AXUIElementCreateApplication(pid)

    def kids(el):
        err, ch = AXUIElementCopyAttributeValue(el, kAXChildrenAttribute, None)
        return list(ch) if ch else []

    def attr(el, name):
        err, v = AXUIElementCopyAttributeValue(el, name, None)
        return v

    texts: List[str] = []
    stack = [root]
    seen = 0
    while stack and seen < 350:
        el = stack.pop(0)
        seen += 1
        for key in (kAXTitleAttribute, kAXValueAttribute, kAXRoleAttribute):
            val = attr(el, key)
            if str(val or "").strip():
                texts.append(str(val).strip())
        stack.extend(kids(el))

    blocker = detect_setup_blocker(app=app_name, observation_texts=texts)
    if blocker is None:
        return True, None
    return False, blocker
