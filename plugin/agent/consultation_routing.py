"""Resolve which auxiliary task (model pin) a consultation should use.

Live failure class (032207): text-only authorship rode ``task=perception``
after the launcher pinned ``HERMES_PERCEPTION_MODEL`` to a vision model
(``qwen3.5:cloud``). The brain chose the right capability, then froze on a
cloud VL query-author call and never typed.

Resolution is modality-first, usecase-second:

* messages with image parts → multimodal stack (perception / screen_understanding)
* text-only messages → text stack (decision / inference), never a vision task

Callers may still pass a legacy ``task="perception"`` for text judgments; this
module remaps them. Explicit ``honor_requested_task=True`` skips remapping.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Sequence


class Modality(str, Enum):
    TEXT = "text"
    MULTIMODAL = "multimodal"


# Logical consultation usecases. Keep these stable; they are the eval contract.
TEXT_USECASES = frozenset(
    {
        "compose_search_query",
        "query_author",
        "decision",
        "decision_choice",
        "meta_choice",
        "decision_high_risk",
        "branch_strategy",
        "resolve_entity",
        "entity_resolution",
        "content_object_resolution",
        "critic_coherence",
        "surface_transition",
        "confirmation",
        "inference",
        "chat_runtime",
    }
)

MULTIMODAL_USECASES = frozenset(
    {
        "perception",
        "screen_understanding",
        "screen_perception",
        "vision",
        "browser_vision",
        "unified_cognition",
        "fusion",
        "computer_use",
        "computer",
        "gui",
    }
)

# Auxiliary task names that resolve through vision / perception env pins.
_VISION_TASKS = frozenset(
    {
        "perception",
        "screen_understanding",
        "screen_perception",
        "vision",
        "browser_vision",
        "unified_cognition",
        "fusion",
    }
)

_DEFAULT_TEXT_TASK = "decision"
_DEFAULT_MULTIMODAL_TASK = "perception"

_USECASE_TEXT_TASK: Dict[str, str] = {
    "compose_search_query": "decision",
    "query_author": "decision",
    "decision_choice": "decision",
    "meta_choice": "decision",
    "decision": "decision",
    "decision_high_risk": "decision_high_risk",
    "branch_strategy": "decision",
    "resolve_entity": "decision",
    "entity_resolution": "decision",
    "content_object_resolution": "content_object_resolution",
    "critic_coherence": "decision",
    "surface_transition": "decision",
    "confirmation": "decision",
    "inference": "inference",
    "chat_runtime": "inference",
}

_USECASE_MULTIMODAL_TASK: Dict[str, str] = {
    "perception": "perception",
    "screen_understanding": "screen_understanding",
    "screen_perception": "perception",
    "vision": "vision",
    "browser_vision": "vision",
    "unified_cognition": "perception",
    "fusion": "perception",
    "computer_use": "computer_use",
    "computer": "computer_use",
    "gui": "computer_use",
}

# Real auxiliary task names on the text stack (env: HERMES_<TASK>_MODEL).
_REAL_TEXT_TASKS = frozenset(
    {
        "decision",
        "decision_high_risk",
        "inference",
        "content_object_resolution",
        "chat_runtime",
    }
)


@dataclass(frozen=True)
class ReasoningRoute:
    """Resolved consultation route after modality / usecase constraints."""

    task: str
    modality: Modality
    usecase: str
    reason: str
    requested_task: str = ""
    remapped: bool = False
    constraints: tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "modality": self.modality.value,
            "usecase": self.usecase,
            "reason": self.reason,
            "requested_task": self.requested_task,
            "remapped": self.remapped,
            "constraints": list(self.constraints),
        }


def _normalize(name: str) -> str:
    return str(name or "").strip().lower().replace("-", "_").replace(" ", "_")


def messages_require_vision(messages: Sequence[Mapping[str, Any]] | None) -> bool:
    """True when any message content part is an image (or image_url)."""
    for msg in messages or ():
        if not isinstance(msg, Mapping):
            continue
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                ptype = str(part.get("type") or "").strip().lower()
                if ptype in {"image_url", "image", "input_image"}:
                    return True
                if part.get("image_url") or part.get("image"):
                    return True
        elif isinstance(content, Mapping):
            ptype = str(content.get("type") or "").strip().lower()
            if ptype in {"image_url", "image", "input_image"}:
                return True
    return False


def detect_modality(messages: Sequence[Mapping[str, Any]] | None) -> Modality:
    return Modality.MULTIMODAL if messages_require_vision(messages) else Modality.TEXT


def classify_usecase(name: str) -> Modality:
    """Declared modality for a logical usecase (independent of message pixels)."""
    key = _normalize(name)
    if key in MULTIMODAL_USECASES or key in _VISION_TASKS:
        return Modality.MULTIMODAL
    if key in TEXT_USECASES:
        return Modality.TEXT
    # Unknown names default to text — safer than accidentally hitting vision pins.
    return Modality.TEXT


def is_vision_task(task: str) -> bool:
    return _normalize(task) in _VISION_TASKS


def _env_model_for_task(task: str) -> str:
    key = _normalize(task).upper()
    if not key:
        return ""
    for prefix in (f"HERMES_{key}", f"HERMES_AUXILIARY_{key}"):
        raw = str(os.getenv(f"{prefix}_MODEL", "") or "").strip()
        if raw:
            return raw
    return ""


def model_looks_vision(model: str) -> bool:
    """Heuristic: model slug is a VLM / vision SoT rather than a text LLM."""
    low = str(model or "").strip().lower()
    if not low:
        return False
    markers = (
        ":vl",
        "-vl",
        "vision",
        "minicpm-v",
        "llava",
        "moondream",
        "qwen3.5:cloud",  # launcher vision escalate SoT
        "qwen3-vl",
    )
    if any(m in low for m in markers):
        return True
    family = low.split(":", 1)[0]
    return family in {"qwen3-vl", "llava", "minicpm-v", "moondream"}


def perception_is_vision_pinned() -> bool:
    """True when the perception env pin points at a vision model."""
    return model_looks_vision(_env_model_for_task("perception"))


def _preferred_text_task(usecase: str) -> str:
    key = _normalize(usecase)
    if key in _USECASE_TEXT_TASK:
        return _USECASE_TEXT_TASK[key]
    if str(os.getenv("HERMES_DECISION_MODEL", "") or "").strip():
        return "decision"
    if str(os.getenv("HERMES_INFERENCE_MODEL", "") or "").strip():
        return "inference"
    return _DEFAULT_TEXT_TASK


def _preferred_multimodal_task(usecase: str) -> str:
    key = _normalize(usecase)
    return _USECASE_MULTIMODAL_TASK.get(key, _DEFAULT_MULTIMODAL_TASK)


def resolve_reasoning_route(
    requested_task: str,
    messages: Sequence[Mapping[str, Any]] | None = None,
    *,
    usecase: Optional[str] = None,
    honor_requested_task: bool = False,
) -> ReasoningRoute:
    """Pick the auxiliary task for one consultation.

    Constraints (always enforced unless ``honor_requested_task``):

    1. ``text_messages_must_not_use_vision_task`` — text-only prompts never
       ride perception/vision pins (fixes compose-author / decision-chooser
       hanging on ``qwen3.5:cloud``).
    2. ``multimodal_messages_must_use_vision_task`` — prompts with image parts
       must use a vision/perception task so pixels are not dropped.
    3. ``usecase_modality_alignment`` — declared text usecases prefer the
       decision/inference stack even when the caller still says ``perception``.
    """
    req = _normalize(requested_task) or _DEFAULT_TEXT_TASK
    use = _normalize(usecase) if usecase else req
    modality = detect_modality(messages)

    if honor_requested_task:
        return ReasoningRoute(
            task=req,
            modality=modality,
            usecase=use,
            reason="honor_requested_task",
            requested_task=req,
            remapped=False,
            constraints=("honor_requested_task",),
        )

    if modality == Modality.TEXT:
        if is_vision_task(req):
            target = _preferred_text_task(use)
            return ReasoningRoute(
                task=target,
                modality=modality,
                usecase=use,
                reason="remapped_text_off_vision_task",
                requested_task=req,
                remapped=True,
                constraints=(
                    "text_messages_must_not_use_vision_task",
                    "usecase_modality_alignment",
                ),
            )
        if req in _REAL_TEXT_TASKS:
            return ReasoningRoute(
                task=req,
                modality=modality,
                usecase=use,
                reason="text_task_unchanged",
                requested_task=req,
                remapped=False,
                constraints=(),
            )
        # Logical usecase name used as task (e.g. compose_search_query).
        if req in TEXT_USECASES or req in _USECASE_TEXT_TASK:
            target = _preferred_text_task(req)
            return ReasoningRoute(
                task=target,
                modality=modality,
                usecase=use,
                reason="text_usecase_to_text_task" if target != req else "text_task_unchanged",
                requested_task=req,
                remapped=target != req,
                constraints=("usecase_modality_alignment",) if target != req else (),
            )
        return ReasoningRoute(
            task=req,
            modality=modality,
            usecase=use,
            reason="text_task_unchanged",
            requested_task=req,
            remapped=False,
            constraints=(),
        )

    # Multimodal messages: must land on a vision-capable task.
    if is_vision_task(req):
        return ReasoningRoute(
            task=req,
            modality=modality,
            usecase=use,
            reason="multimodal_task_unchanged",
            requested_task=req,
            remapped=False,
            constraints=(),
        )
    target = _preferred_multimodal_task(use if use in MULTIMODAL_USECASES else "perception")
    return ReasoningRoute(
        task=target,
        modality=modality,
        usecase=use,
        reason="remapped_multimodal_onto_vision_task",
        requested_task=req,
        remapped=True,
        constraints=("multimodal_messages_must_use_vision_task",),
    )
