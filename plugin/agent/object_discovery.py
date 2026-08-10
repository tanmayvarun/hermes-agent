"""Generic goal-conditioned object discovery.

Adapters expose visible objects. This module scores those objects against a
goal, optionally asks a reasoning-capable LLM to rerank ambiguous candidates,
and returns a binding decision that downstream task logic can consume.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, is_dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence

from plugin.agent.goal import Goal
from plugin.agent.reasoning_consultation import consult_reasoning
from plugin.worldmodel.content import (
    ContentObject,
    ContentQuery,
    DiscoveryContext,
    ObjectResolution,
    RankedContentObject,
    content_objects_from_rows,
)

logger = logging.getLogger(__name__)

_CACHE_ATTR = "last_object_resolution"
_LLM_SCORE_THRESHOLD = 0.84


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass
    return str(value)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _truncate(value: Any, limit: int = 180) -> str:
    text = _clean(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())


def _tokenize(value: Any) -> List[str]:
    raw = _clean(value).lower()
    if not raw:
        return []
    return [tok for tok in re.split(r"[^a-z0-9]+", raw) if tok]


def _extract_text(response: Any) -> str:
    if isinstance(response, str):
        return response.strip()
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip()
    if isinstance(response, dict):
        for key in ("output_text", "text", "content"):
            val = response.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return str(response).strip()


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _main_runtime_snapshot() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        model_cfg = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
        provider = str(model_cfg.get("provider") or "").strip()
        model = str(model_cfg.get("default") or model_cfg.get("model") or "").strip()
        runtime: Dict[str, Any] = {}
        if provider:
            runtime["provider"] = provider
        if model:
            runtime["model"] = model
        return runtime
    except Exception:
        return {}


def build_content_query(goal: Goal) -> ContentQuery:
    kind = (goal.kind or "").strip().lower()
    semantic_reference = _clean(goal.link_query or goal.target_contact or goal.contact or goal.prompt or goal.description)
    if kind.endswith("forward_message") or "forward" in kind:
        target_types = ["link", "message_with_link", "message"]
        desired_operation = "forward"
    elif "message" in kind or "read" in kind:
        target_types = ["message", "message_with_link", "link"]
        desired_operation = "read"
    else:
        target_types = []
        desired_operation = ""

    aliases: List[str] = []
    seen = set()
    for candidate in (
        semantic_reference,
        semantic_reference.replace("-", " "),
        semantic_reference.replace("_", " "),
        semantic_reference.replace(" ", ""),
        goal.link_query,
    ):
        cleaned = _clean(candidate)
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            aliases.append(cleaned)

    return ContentQuery(
        raw=_clean(goal.prompt or goal.description or semantic_reference),
        semantic_reference=semantic_reference,
        target_types=target_types,
        source_container=_clean(goal.contact),
        source_container_type="conversation" if goal.contact else "",
        desired_operation=desired_operation,
        destination=_clean(goal.target_contact),
        semantic_aliases=aliases,
        context_hypotheses=list(goal.intent_hypotheses()),
        prompt=_clean(goal.prompt),
        goal_kind=goal.kind,
    )


def _url_tokens(obj: ContentObject) -> List[str]:
    identity = obj.url_identity
    tokens: List[str] = []
    for key in ("host_tokens", "path_tokens", "query_tokens"):
        tokens.extend([tok for tok in identity.get(key) or [] if tok])
    registrable = identity.get("registrable_domain") or ""
    if registrable:
        tokens.extend(_tokenize(registrable))
    return [tok for tok in tokens if tok]


def _all_text_blobs(obj: ContentObject) -> List[str]:
    return [
        _clean(obj.text),
        _clean(obj.title),
        _clean(obj.filename),
        _clean(obj.sender),
        _clean(obj.container_id),
        _clean(obj.container_type),
        _clean(obj.url),
        _clean(obj.text_blob()),
    ]


def _match_score(needle: str, haystack: str) -> float:
    n = _compact(needle)
    h = _compact(haystack)
    if not n or not h:
        return 0.0
    if n == h:
        return 1.0
    if n in h or h in n:
        return 0.9
    return SequenceMatcher(None, n, h).ratio()


def _source_container_match(query: ContentQuery, obj: ContentObject) -> float:
    source = _clean(query.source_container)
    if not source:
        return 0.0
    candidates = [
        obj.container_id,
        obj.container_type,
        obj.sender or "",
        obj.metadata.get("container_title") or "",
        obj.metadata.get("container_name") or "",
        obj.metadata.get("sender") or "",
    ]
    best = 0.0
    for candidate in candidates:
        best = max(best, _match_score(source, candidate))
    return best


def _type_match(query: ContentQuery, obj: ContentObject) -> float:
    if not query.target_types:
        return 0.0
    target = obj.object_type.lower().strip()
    targets = {t.lower().strip() for t in query.target_types if t}
    if target in targets:
        return 1.0
    if target == "message_with_link" and {"link", "message"} & targets:
        return 0.9
    if obj.url and {"link", "message_with_link", "message"} & targets:
        return 0.75
    if target == "message" and "message" in targets:
        return 0.8
    return 0.0


def _semantic_match(query: ContentQuery, obj: ContentObject) -> float:
    ref = _clean(query.semantic_reference)
    if not ref:
        return 0.0
    blobs = _all_text_blobs(obj)
    best = 0.0
    ref_tokens = _tokenize(ref)
    for blob in blobs:
        if not blob:
            continue
        best = max(best, _match_score(ref, blob))
        blob_compact = _compact(blob)
        if _compact(ref) in blob_compact or blob_compact in _compact(ref):
            best = max(best, 0.95)
        if ref and ref.lower() in blob.lower():
            best = max(best, 0.98)
        blob_tokens = _tokenize(blob)
        if ref_tokens and all(token in blob_tokens for token in ref_tokens):
            best = max(best, 0.9)
    for alias in query.semantic_aliases:
        alias = _clean(alias)
        if not alias:
            continue
        for blob in blobs:
            if not blob:
                continue
            if alias.lower() in blob.lower() or _compact(alias) in _compact(blob):
                best = max(best, 0.9)
    if obj.url:
        url_tokens = _url_tokens(obj)
        if ref_tokens and all(tok in url_tokens for tok in ref_tokens):
            best = max(best, 1.0)
        if any(tok in url_tokens for tok in ref_tokens):
            best = max(best, 0.95)
    return best


def _operation_compatibility(query: ContentQuery, obj: ContentObject) -> float:
    op = _clean(query.desired_operation).lower()
    if not op:
        return 0.0
    if op == "forward":
        if obj.object_type in {"link", "message_with_link"} or obj.url:
            return 1.0
        if obj.object_type == "message":
            return 0.55
        return 0.1
    if op in {"read", "inspect"}:
        return 0.7 if obj.text or obj.title or obj.url else 0.2
    return 0.35


def _context_match(query: ContentQuery, obj: ContentObject) -> float:
    best = 0.0
    for hint in query.context_hypotheses:
        hint = _clean(hint)
        if not hint:
            continue
        for blob in _all_text_blobs(obj):
            if not blob:
                continue
            best = max(best, _match_score(hint, blob))
    return best


def _content_identity_required(query: ContentQuery) -> bool:
    """True when semantic_reference is a content/link query, not merely a contact."""
    ref = _clean(query.semantic_reference)
    if not ref:
        return False
    kind = _clean(query.goal_kind).lower()
    if "forward" in kind or "message" in kind or "link" in kind:
        # link_query is preferred into semantic_reference by build_content_query.
        return True
    return bool(query.target_types)


def _enforce_content_identity(
    query: ContentQuery,
    resolution: ObjectResolution,
    visible: Sequence[ContentObject],
) -> ObjectResolution:
    """High-precision gate after deterministic or LLM selection."""
    if not _content_identity_required(query):
        return resolution
    try:
        from plugin.agent.source_query_binding import (
            host_contradicts_query,
            query_supported_by_text,
        )
    except Exception:
        return resolution

    ref = _clean(query.semantic_reference)
    by_id = {str(obj.id): obj for obj in visible}
    selected_id = str(resolution.selected_object_id or "")
    selected_obj = by_id.get(selected_id)
    if selected_obj is None and resolution.selected_source_entity_ids:
        want = set(int(x) for x in resolution.selected_source_entity_ids)
        for obj in visible:
            if any(int(x) in want for x in (obj.source_entity_ids or [])):
                selected_obj = obj
                break
    if selected_obj is None:
        return resolution
    blob = _object_text_blob(selected_obj)
    if query_supported_by_text(blob, ref) and not (
        host_contradicts_query(blob, ref) and not query_supported_by_text(blob, ref)
    ):
        return resolution
    # Prefer any other visible object that actually supports the query.
    for obj in visible:
        cand_blob = _object_text_blob(obj)
        if query_supported_by_text(cand_blob, ref):
            return ObjectResolution(
                status="resolved",
                selected_object_id=obj.id,
                candidates=list(resolution.candidates or []),
                confidence=max(0.7, float(resolution.confidence or 0.0)),
                evidence=list(resolution.evidence or []) + ["identity_gate_reselected"],
                next_information_actions=[],
                selected_source_entity_ids=list(obj.source_entity_ids or []),
                selected_object_text=obj.display_text,
                raw={
                    **_json_safe(resolution.raw or {}),
                    "identity_gate": "reselected",
                    "rejected_object_id": selected_id,
                },
            )
    return ObjectResolution(
        status="not_found",
        selected_object_id=None,
        candidates=list(resolution.candidates or []),
        confidence=0.0,
        evidence=list(resolution.evidence or []) + ["identity_gate_rejected"],
        next_information_actions=[
            "search_within_container",
            "scroll_timeline",
            "inspect_more_context",
        ],
        selected_source_entity_ids=[],
        selected_object_text="",
        raw={
            **_json_safe(resolution.raw or {}),
            "identity_gate": "rejected",
            "binding_blocked": True,
            "contradictions": ["semantic_query_unsupported"],
            "rejected_object_id": selected_id,
        },
    )


def _object_text_blob(obj: ContentObject) -> str:
    parts = [
        getattr(obj, "text", ""),
        getattr(obj, "title", ""),
        getattr(obj, "url", ""),
        getattr(obj, "filename", ""),
        getattr(obj, "display_text", ""),
    ]
    meta = getattr(obj, "metadata", None) or {}
    if isinstance(meta, dict):
        parts.append(meta.get("description") or "")
    return " ".join(_clean(p) for p in parts if p)


def _score_object(query: ContentQuery, obj: ContentObject) -> RankedContentObject:
    score = 0.0
    reasons: List[str] = []
    contradictions: List[str] = []

    if obj.visible:
        score += 0.03
    if obj.confidence:
        score += min(0.05, max(0.0, float(obj.confidence)) * 0.02)

    sem = _semantic_match(query, obj)
    if sem >= 0.95:
        score += 0.42
        reasons.append("semantic_exact_match")
    elif sem >= 0.85:
        score += 0.32
        reasons.append("semantic_strong_match")
    elif sem >= 0.65:
        score += 0.18
        reasons.append("semantic_partial_match")

    if obj.url:
        url_identity = obj.url_identity
        ref = _clean(query.semantic_reference)
        if ref and ref.lower() in (url_identity.get("registrable_domain") or "").lower():
            score += 0.4
            reasons.append("url_domain_match")
        host_tokens = set(url_identity.get("host_tokens") or [])
        path_tokens = set(url_identity.get("path_tokens") or [])
        query_tokens = set(_tokenize(ref))
        if query_tokens and query_tokens <= (host_tokens | path_tokens):
            score += 0.25
            reasons.append("url_token_match")
        elif query_tokens and query_tokens & (host_tokens | path_tokens):
            score += 0.12
            reasons.append("url_partial_token_match")

    typ = _type_match(query, obj)
    if typ >= 0.95:
        score += 0.25
        reasons.append("object_type_exact")
    elif typ >= 0.7:
        score += 0.18
        reasons.append("object_type_compatible")

    src = _source_container_match(query, obj)
    if src >= 0.95:
        score += 0.22
        reasons.append("source_container_exact")
    elif src >= 0.75:
        score += 0.15
        reasons.append("source_container_close")

    ctx = _context_match(query, obj)
    if ctx >= 0.95:
        score += 0.16
        reasons.append("context_exact")
    elif ctx >= 0.75:
        score += 0.09
        reasons.append("context_close")

    op = _operation_compatibility(query, obj)
    if op >= 0.95:
        score += 0.08
        reasons.append("operation_compatible")
    elif op >= 0.5:
        score += 0.04
        reasons.append("operation_plausible")

    if obj.sender and _semantic_match(query, ContentObject(
        id=obj.id,
        object_type=obj.object_type,
        text=obj.sender,
        title=obj.sender,
        container_id=obj.container_id,
        container_type=obj.container_type,
        source_app=obj.source_app,
    )) >= 0.85:
        score += 0.05
        reasons.append("sender_match")

    # High-precision identity gate: container+type relevance must not bind a
    # distractor URL (live 214025: YouTube in Pallavi ≠ zarooratwala).
    if _content_identity_required(query):
        try:
            from plugin.agent.source_query_binding import (
                evaluate_source_object_match,
                host_contradicts_query,
                query_supported_by_text,
            )

            blob = _object_text_blob(obj)
            ref = _clean(query.semantic_reference)
            gm = evaluate_source_object_match(
                text=blob,
                kind=str(getattr(obj, "object_type", "") or ""),
                query=ref,
                container_open=str(getattr(obj, "container_id", "") or ""),
                expected_container=_clean(query.source_container),
                perception_matches_goal=False,
            )
            if host_contradicts_query(blob, ref) and not query_supported_by_text(blob, ref):
                score = 0.0
                contradictions.append("url_host_contradicts_query")
                reasons.append("binding_ineligible_host_mismatch")
            elif not gm.semantic_query_match:
                # Keep as low-recall candidate; never win final binding.
                score = min(score, 0.12)
                contradictions.append("semantic_query_absent")
                reasons.append("binding_ineligible_query_absent")
            else:
                reasons.append("semantic_query_supported")
                score = min(1.0, score + 0.15)
        except Exception:
            pass

    score = max(0.0, min(1.0, score))
    if not reasons:
        reasons.append("weak_candidate")
    if contradictions:
        reasons.extend(contradictions)
    return RankedContentObject(object_id=obj.id, score=round(score, 4), reasons=reasons, object=obj)


def _resolution_cache_key(query: ContentQuery, context: DiscoveryContext, objects: Sequence[ContentObject]) -> str:
    payload = {
        "query": query.to_dict(),
        "context": context.to_dict(),
        "objects": [
            {
                "id": obj.id,
                "object_type": obj.object_type,
                "text": _clean(obj.text),
                "title": _clean(obj.title),
                "url": _clean(obj.url),
                "filename": _clean(obj.filename),
                "sender": _clean(obj.sender),
                "container_id": _clean(obj.container_id),
                "container_type": _clean(obj.container_type),
                "source_app": _clean(obj.source_app),
                "source_entity_ids": list(obj.source_entity_ids),
                "visible": bool(obj.visible),
            }
            for obj in objects
        ],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# Static across every call, so it lives in the system message where a provider
# can cache the prefix, rather than being re-sent inside the per-call user JSON.
_RESOLUTION_SYSTEM_PROMPT = (
    "You are a generic object-discovery synthesizer. You interpret normalized "
    "content objects from accessibility-derived rows. Given a goal query and a "
    "collection of visible content objects, select the object that best "
    "satisfies the goal. The adapter already exposed the visible objects; do "
    "not invent hidden ones, ids, or app-specific step plans.\n"
    "\n"
    "Return only strict JSON with keys: summary, confidence, "
    "selected_object_id, ranked_objects, selected_source_entity_ids, "
    "selected_object_text, supporting_evidence, contradictions, "
    "next_information_actions, needs_followup_observe. Each ranked_objects item "
    "must include object_id, score, and reason. Prefer the object whose "
    "identity and container best match the goal."
)


def _build_prompt(
    query: ContentQuery,
    context: DiscoveryContext,
    objects: Sequence[ContentObject],
    *,
    window: int,
) -> List[Dict[str, Any]]:
    payload = {
        "query": query.to_dict(),
        "context": context.to_dict(),
        "objects": [
            {
                "object_id": obj.id,
                "object_type": obj.object_type,
                "display_text": _truncate(obj.display_text, 140),
                "text": _truncate(obj.text, 220),
                "title": _truncate(obj.title, 140),
                "url": _truncate(obj.url, 180),
                "sender": _truncate(obj.sender, 80),
                "container_id": _truncate(obj.container_id, 80),
                "container_type": _truncate(obj.container_type, 48),
                "source_app": _truncate(obj.source_app, 32),
                "source_entity_ids": list(obj.source_entity_ids),
                "visible": bool(obj.visible),
                "metadata": {
                    k: _json_safe(v)
                    for k, v in (obj.metadata or {}).items()
                    if k in {"description", "label", "role", "entity_type", "blob", "url_identity", "container_title"}
                },
            }
            for obj in objects[:window]
        ],
    }
    return [
        {
            "role": "system",
            "content": _RESOLUTION_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        },
    ]


def _parse_llm_resolution(parsed: Dict[str, Any], objects: Sequence[ContentObject]) -> ObjectResolution:
    obj_by_id = {str(obj.id): obj for obj in objects}
    ranked: List[RankedContentObject] = []
    raw_ranked = parsed.get("ranked_objects") or parsed.get("ranked_messages") or parsed.get("ranked_rows") or []
    if isinstance(raw_ranked, list):
        for item in raw_ranked:
            if not isinstance(item, dict):
                continue
            obj_id = str(item.get("object_id") or item.get("id") or item.get("entity_id") or "").strip()
            if not obj_id:
                continue
            obj = obj_by_id.get(obj_id)
            if obj is None:
                continue
            try:
                score = float(item.get("score") or item.get("confidence") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            ranked.append(
                RankedContentObject(
                    object_id=obj_id,
                    score=max(0.0, min(1.0, score)),
                    reasons=[
                        str(item.get("reason") or item.get("why") or "").strip() or "llm_ranked",
                    ],
                    object=obj,
                )
            )

    selected_id = str(parsed.get("selected_object_id") or parsed.get("object_id") or "").strip()
    if not selected_id and ranked:
        selected_id = ranked[0].object_id
    if selected_id and selected_id not in obj_by_id:
        raise RuntimeError(f"LLM selected unknown object id {selected_id!r}")
    selected_obj = obj_by_id.get(selected_id) if selected_id else None

    if not ranked:
        ranked = [RankedContentObject(object_id=obj.id, score=0.0, reasons=["llm_unranked"], object=obj) for obj in objects[:5]]

    confidence_raw = parsed.get("confidence", parsed.get("score", 0.0))
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw or 0.0)))
    except (TypeError, ValueError):
        confidence = ranked[0].score if ranked else 0.0

    evidence = [str(x) for x in (parsed.get("supporting_evidence") or parsed.get("evidence") or []) if str(x)]
    contradictions = [str(x) for x in (parsed.get("contradictions") or []) if str(x)]
    next_actions = [str(x) for x in (parsed.get("next_information_actions") or []) if str(x)]
    selected_source_entity_ids = [int(x) for x in (parsed.get("selected_source_entity_ids") or []) if str(x).strip()]
    if not selected_source_entity_ids and selected_obj is not None:
        selected_source_entity_ids = list(selected_obj.source_entity_ids)

    selected_text = str(parsed.get("selected_object_text") or "").strip()
    if not selected_text and selected_obj is not None:
        selected_text = selected_obj.display_text

    if selected_id and confidence >= 0.8:
        status = "resolved"
    elif selected_id and confidence >= 0.55:
        status = "ambiguous"
    elif ranked:
        status = "needs_more_context" if bool(parsed.get("needs_followup_observe")) else "ambiguous"
    else:
        status = "not_found"

    return ObjectResolution(
        status=status,
        selected_object_id=selected_id or None,
        candidates=ranked,
        confidence=confidence,
        evidence=evidence,
        next_information_actions=next_actions,
        selected_source_entity_ids=selected_source_entity_ids,
        selected_object_text=selected_text,
        raw=parsed,
    )


class ObjectDiscoveryEngine:
    """Generic object-ranking core used by app adapters and task binders."""

    def resolve(
        self,
        query: ContentQuery,
        objects: Sequence[ContentObject],
        *,
        context: Optional[DiscoveryContext] = None,
        world: Any = None,
        force_llm: bool = False,
    ) -> ObjectResolution:
        context = context or DiscoveryContext()
        visible = [obj for obj in objects if bool(obj.visible)]
        if not visible:
            return ObjectResolution(status="not_found", confidence=0.0, raw={"reason": "no_visible_objects"})

        cache_key = _resolution_cache_key(query, context, visible)
        cached = getattr(world, _CACHE_ATTR, None) if world is not None else None
        if isinstance(cached, dict) and cached.get("cache_key") == cache_key:
            raw = cached.get("summary")
            if isinstance(raw, dict):
                return _parse_llm_resolution(raw, visible)

        ranked = sorted(
            (_score_object(query, obj) for obj in visible),
            key=lambda item: (-float(item.score or 0.0), item.object_id),
        )

        top_score = float(ranked[0].score or 0.0) if ranked else 0.0
        second_score = float(ranked[1].score or 0.0) if len(ranked) > 1 else 0.0
        gap = top_score - second_score
        # An explicit ``force_llm`` from the caller always consults the model:
        # the caller (e.g. conversation ranking) has decided it wants semantic
        # arbitration, and the prompt carries context the deterministic scorer
        # cannot use. The *heuristic* escalation (a low or ambiguous score) is
        # what stays gated on having more than one candidate to arbitrate — a
        # lone survivor has nothing to disambiguate against.
        should_rerank = bool(
            force_llm
            or (
                len(ranked) > 1
                and context.use_llm
                and (top_score < _LLM_SCORE_THRESHOLD or gap < 0.18)
            )
        )
        if should_rerank:
            consultation = None
            try:
                consultation = consult_reasoning(
                    "content_object_resolution",
                    _build_prompt(query, context, [item.object or visible[0] for item in ranked], window=min(8, len(ranked))),
                    call_kwargs={
                        "task": "content_object_resolution",
                        "main_runtime": _main_runtime_snapshot(),
                    },
                    temperature=0.1,
                    max_tokens=256,
                )
            except Exception:
                consultation = None
            parsed = consultation.parsed if consultation is not None else None
            if parsed:
                resolution = _parse_llm_resolution(parsed, visible)
                resolution.raw = {
                    **_json_safe(resolution.raw),
                    "consultation": consultation.to_dict(include_messages=False),
                }
                resolution = _enforce_content_identity(query, resolution, visible)
                if world is not None:
                    setattr(world, _CACHE_ATTR, {"cache_key": cache_key, "summary": resolution.to_dict()})
                return resolution
            # The model was unavailable or returned no usable JSON. The caller
            # asked for arbitration; when the model cannot answer we degrade to
            # the deterministic ranked pick below rather than crashing the loop.

        if not ranked:
            resolution = ObjectResolution(status="not_found", confidence=0.0, raw={"reason": "no_ranked_candidates"})
        else:
            best = ranked[0]
            selected_obj = best.object
            confidence = float(best.score or 0.0)
            # Identity-sensitive queries: never elevate a distractor that only
            # matches container/type (YouTube in the right chat).
            binding_blocked = False
            if _content_identity_required(query):
                reasons_l = {str(r).lower() for r in (best.reasons or [])}
                if (
                    "binding_ineligible_host_mismatch" in reasons_l
                    or "binding_ineligible_query_absent" in reasons_l
                    or confidence < 0.35
                ):
                    binding_blocked = True
            if binding_blocked:
                blocked_reasons = [
                    r
                    for r in (best.reasons or [])
                    if "ineligible" in str(r).lower() or "contradict" in str(r).lower()
                ] or ["semantic_query_unsupported"]
                resolution = ObjectResolution(
                    status="not_found",
                    selected_object_id=None,
                    candidates=ranked,
                    confidence=0.0,
                    evidence=list(best.reasons),
                    next_information_actions=[
                        "search_within_container",
                        "scroll_timeline",
                        "inspect_more_context",
                    ],
                    selected_source_entity_ids=[],
                    selected_object_text="",
                    raw={
                        "cache_key": cache_key,
                        "top_score": top_score,
                        "gap": gap,
                        "deterministic": True,
                        "binding_blocked": True,
                        "contradictions": blocked_reasons,
                    },
                )
            else:
                status = "resolved" if confidence >= 0.8 and gap >= 0.08 else "ambiguous"
                evidence = list(best.reasons)
                next_actions = []
                if status != "resolved":
                    next_actions = ["inspect_more_context", "search_within_container", "open_candidate"]
                resolution = ObjectResolution(
                    status=status,
                    selected_object_id=best.object_id,
                    candidates=ranked,
                    confidence=confidence,
                    evidence=evidence,
                    next_information_actions=next_actions,
                    selected_source_entity_ids=list(
                        selected_obj.source_entity_ids if selected_obj is not None else []
                    ),
                    selected_object_text="" if selected_obj is None else selected_obj.display_text,
                    raw={
                        "cache_key": cache_key,
                        "top_score": top_score,
                        "gap": gap,
                        "deterministic": True,
                    },
                )
                resolution = _enforce_content_identity(query, resolution, visible)

        if world is not None:
            setattr(world, _CACHE_ATTR, {"cache_key": cache_key, "summary": resolution.to_dict()})
        return resolution


_ENGINE: Optional[ObjectDiscoveryEngine] = None


def get_object_discovery_engine() -> ObjectDiscoveryEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ObjectDiscoveryEngine()
    return _ENGINE


def resolve_content_objects(
    query: ContentQuery,
    objects: Sequence[ContentObject],
    *,
    context: Optional[DiscoveryContext] = None,
    world: Any = None,
    force_llm: bool = False,
) -> ObjectResolution:
    return get_object_discovery_engine().resolve(
        query,
        objects,
        context=context,
        world=world,
        force_llm=force_llm,
    )


def resolve_content_rows(
    goal: Goal,
    rows: Sequence[Dict[str, Any]],
    *,
    source_app: str = "",
    container_id: str = "",
    container_type: str = "conversation",
    context: Optional[DiscoveryContext] = None,
    world: Any = None,
    force_llm: bool = False,
) -> ObjectResolution:
    query = build_content_query(goal)
    objects = content_objects_from_rows(rows, source_app=source_app, container_id=container_id, container_type=container_type)
    return resolve_content_objects(query, objects, context=context, world=world, force_llm=force_llm)
