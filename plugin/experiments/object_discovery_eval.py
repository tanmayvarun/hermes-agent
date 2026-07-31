"""Synthetic evals for generic content-object discovery.

This benchmark uses synthesized message rows so we can measure whether the
generic object-discovery core selects the right evidence under noise, and how
much of the gold evidence it retrieves in its top-k ranking.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from plugin.agent.goal import Goal
from plugin.agent.object_discovery import DiscoveryContext, resolve_content_rows


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass
    return str(value)


def _message_row(
    entity_id: int,
    *,
    text: str = "",
    label: str = "",
    description: str = "",
    url: str = "",
    sender: str = "Shishir",
    role: str = "AXStaticText",
    entity_type: str = "static",
    visible: bool = True,
    title: str = "",
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "entity_id": entity_id,
        "text": text,
        "label": label or text,
        "description": description,
        "url": url,
        "sender": sender,
        "role": role,
        "entity_type": entity_type,
        "visible": visible,
    }
    if title:
        row["title"] = title
    return row


@dataclass
class ObjectDiscoveryEvalCase:
    case_id: str
    goal: Goal
    rows: List[Dict[str, Any]]
    gold_entity_ids: List[int]
    description: str = ""
    source_app: str = "WhatsApp"
    container_id: str = "Kulvinder Ji"
    container_type: str = "conversation"


@dataclass
class ObjectDiscoveryEvalResult:
    case_id: str
    description: str
    top_k: int
    gold_entity_ids: List[int]
    predicted_entity_ids: List[int]
    selected_entity_id: Optional[int]
    top1_correct: bool
    candidate_precision_at_k: float
    candidate_recall_at_k: float
    candidate_f1_at_k: float
    confidence: float
    status: str
    supporting_evidence: List[str] = field(default_factory=list)
    next_information_actions: List[str] = field(default_factory=list)
    selected_text: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "description": self.description,
            "top_k": self.top_k,
            "gold_entity_ids": list(self.gold_entity_ids),
            "predicted_entity_ids": list(self.predicted_entity_ids),
            "selected_entity_id": self.selected_entity_id,
            "top1_correct": bool(self.top1_correct),
            "candidate_precision_at_k": round(float(self.candidate_precision_at_k or 0.0), 4),
            "candidate_recall_at_k": round(float(self.candidate_recall_at_k or 0.0), 4),
            "candidate_f1_at_k": round(float(self.candidate_f1_at_k or 0.0), 4),
            "confidence": round(float(self.confidence or 0.0), 4),
            "status": self.status,
            "supporting_evidence": list(self.supporting_evidence),
            "next_information_actions": list(self.next_information_actions),
            "selected_text": self.selected_text,
            "raw": _json_safe(self.raw),
        }


@dataclass
class ObjectDiscoveryEvalSummary:
    case_count: int
    top_k: int
    top1_accuracy: float
    micro_candidate_precision_at_k: float
    micro_candidate_recall_at_k: float
    micro_candidate_f1_at_k: float
    macro_candidate_precision_at_k: float
    macro_candidate_recall_at_k: float
    macro_candidate_f1_at_k: float
    total_gold_entities: int
    total_predicted_entities: int
    total_true_positive_entities: int
    cases: List[ObjectDiscoveryEvalResult] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_count": self.case_count,
            "top_k": self.top_k,
            "top1_accuracy": round(float(self.top1_accuracy or 0.0), 4),
            "micro_candidate_precision_at_k": round(float(self.micro_candidate_precision_at_k or 0.0), 4),
            "micro_candidate_recall_at_k": round(float(self.micro_candidate_recall_at_k or 0.0), 4),
            "micro_candidate_f1_at_k": round(float(self.micro_candidate_f1_at_k or 0.0), 4),
            "macro_candidate_precision_at_k": round(float(self.macro_candidate_precision_at_k or 0.0), 4),
            "macro_candidate_recall_at_k": round(float(self.macro_candidate_recall_at_k or 0.0), 4),
            "macro_candidate_f1_at_k": round(float(self.macro_candidate_f1_at_k or 0.0), 4),
            "total_gold_entities": int(self.total_gold_entities),
            "total_predicted_entities": int(self.total_predicted_entities),
            "total_true_positive_entities": int(self.total_true_positive_entities),
            "notes": list(self.notes),
            "cases": [case.to_dict() for case in self.cases],
        }


def _f1(precision: float, recall: float) -> float:
    if precision <= 0.0 or recall <= 0.0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def _candidate_ids_from_resolution(resolution: Any, top_k: int) -> List[int]:
    ids: List[int] = []
    for cand in list(getattr(resolution, "candidates", []) or [])[: max(1, top_k)]:
        obj = getattr(cand, "object", None)
        source_ids = list(getattr(obj, "source_entity_ids", None) or []) if obj is not None else []
        if source_ids:
            entity_id = source_ids[0]
        else:
            object_id = str(getattr(cand, "object_id", "") or "").strip()
            try:
                entity_id = int(object_id)
            except Exception:
                continue
        if entity_id not in ids:
            ids.append(int(entity_id))
    return ids


def _selected_entity_id(resolution: Any) -> Optional[int]:
    ids = list(getattr(resolution, "selected_source_entity_ids", None) or [])
    if ids:
        return int(ids[0])
    selected = str(getattr(resolution, "selected_object_id", "") or "").strip()
    if not selected:
        return None
    try:
        return int(selected)
    except Exception:
        return None


def build_synthetic_cases() -> List[ObjectDiscoveryEvalCase]:
    """Generate message-level retrieval cases that exercise precision/recall."""

    cases: List[ObjectDiscoveryEvalCase] = []

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
        prompt="find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi",
    )
    cases.append(
        ObjectDiscoveryEvalCase(
            case_id="exact_link_message",
            description="Exact content row with URL and preview title should win over reply noise.",
            goal=goal,
            gold_entity_ids=[10, 11],
            rows=[
                _message_row(
                    10,
                    text="ZarooratWala",
                    label="ZarooratWala",
                    description="ZarooratWala - Fresh Groceries Delivered",
                    url="https://www.zarooratwala.com/?utm_source=chat&utm_medium=whatsapp",
                    sender="Kulvinder Ji",
                ),
                _message_row(11, text="ZarooratWala - Fresh Groceries Delivered", label="Link preview", sender="Kulvinder Ji"),
                _message_row(12, text="Thanks", label="Thanks", description="reply only", sender="Kulvinder Ji"),
                _message_row(13, text="Random sale", label="Random sale", url="https://example.com/promo", sender="Shishir"),
            ],
        )
    )

    cases.append(
        ObjectDiscoveryEvalCase(
            case_id="same_domain_distractor",
            description="Same-domain distractor should not displace the actual forwarded evidence.",
            goal=goal,
            gold_entity_ids=[20, 21],
            rows=[
                _message_row(
                    20,
                    text="Shared link",
                    label="Shared link",
                    description="ZarooratWala - Fresh Groceries Delivered",
                    url="https://www.zarooratwala.com/?utm_source=chat&utm_medium=whatsapp",
                    sender="Kulvinder Ji",
                ),
                _message_row(
                    21,
                    text="https://www.zarooratwala.com/?utm_source=chat&utm_medium=whatsapp",
                    label="ZarooratWala",
                    description="ZarooratWala - Fresh Groceries Delivered",
                    url="https://www.zarooratwala.com/?utm_source=chat&utm_medium=whatsapp",
                    sender="Kulvinder Ji",
                ),
                _message_row(
                    22,
                    text="New offer",
                    label="New offer",
                    description="ZarooratWala offers and coupons",
                    url="https://www.zarooratwala.com/offers",
                    sender="Shishir",
                ),
                _message_row(23, text="OK", label="OK", description="reply only", sender="Kulvinder Ji"),
            ],
        )
    )

    cases.append(
        ObjectDiscoveryEvalCase(
            case_id="google_maps_share_link",
            description="The Google Maps share link for a place should be preferred over plain mention noise.",
            goal=Goal(
                kind="whatsapp_forward_message",
                contact="Kulvinder",
                target_contact="Pallavi",
                link_query="india coffee house hsr layout",
                prompt="find the google maps share link of india coffee house hsr layout and share with pallavi",
            ),
            gold_entity_ids=[30, 31],
            rows=[
                _message_row(
                    30,
                    text="India Coffee House HSR Layout",
                    label="India Coffee House HSR Layout",
                    description="Google Maps",
                    url="https://maps.app.goo.gl/example",
                    sender="Kulvinder Ji",
                ),
                _message_row(
                    31,
                    text="https://maps.app.goo.gl/example",
                    label="India Coffee House HSR Layout",
                    description="Share link",
                    url="https://maps.app.goo.gl/example",
                    sender="Kulvinder Ji",
                ),
                _message_row(32, text="I know that place", label="I know that place", sender="Shishir"),
                _message_row(33, text="Map", label="Map", url="https://maps.example/other", sender="Shishir"),
            ],
        )
    )

    cases.append(
        ObjectDiscoveryEvalCase(
            case_id="reply_chain_message",
            description="Reply-only chatter should not beat the message that actually carries the link.",
            goal=goal,
            gold_entity_ids=[40, 41],
            rows=[
                _message_row(40, text="check this out", label="check this out", sender="Kulvinder Ji"),
                _message_row(
                    41,
                    text="ZarooratWala",
                    label="ZarooratWala",
                    description="ZarooratWala - Fresh Groceries Delivered",
                    url="https://www.zarooratwala.com/?utm_source=chat",
                    sender="Kulvinder Ji",
                ),
                _message_row(42, text="nice", label="nice", sender="Kulvinder Ji"),
                _message_row(43, text="forwarded", label="forwarded", description="Forwarded", sender="Shishir"),
            ],
        )
    )

    cases.append(
        ObjectDiscoveryEvalCase(
            case_id="typo_variation",
            description="Goal phrasing with a typo should still recover the exact target message row.",
            goal=Goal(
                kind="whatsapp_forward_message",
                contact="Kulvinder",
                target_contact="Pallavi",
                link_query="zaroortwala",
                prompt="find the zaroortwala link sent to kulvinder on whatsapp and forward to pallavi",
            ),
            gold_entity_ids=[50],
            rows=[
                _message_row(
                    50,
                    text="ZarooratWala",
                    label="ZarooratWala",
                    description="ZarooratWala - Fresh Groceries Delivered",
                    url="https://www.zarooratwala.com/?utm_source=chat",
                    sender="Kulvinder Ji",
                ),
                _message_row(
                    51,
                    text="ZaroortWala",
                    label="ZaroortWala",
                    description="Misc promo",
                    url="https://zaroortwala.example/",
                    sender="Shishir",
                ),
                _message_row(52, text="typo mention", label="typo mention", sender="Kulvinder Ji"),
            ],
        )
    )

    cases.append(
        ObjectDiscoveryEvalCase(
            case_id="source_conversation_context",
            description="Rows from the source conversation should be favored over unrelated sidebar chatter.",
            goal=goal,
            gold_entity_ids=[60],
            rows=[
                _message_row(60, text="ZarooratWala", label="ZarooratWala", description="Fresh Groceries Delivered", url="https://www.zarooratwala.com/?utm_source=chat", sender="Kulvinder Ji"),
                _message_row(61, text="Hey", label="Hey", sender="Pallavi"),
                _message_row(62, text="Kulvinder in group", label="Kulvinder in group", description="group mention", sender="Shishir"),
            ],
        )
    )

    return cases


def evaluate_case(
    case: ObjectDiscoveryEvalCase,
    *,
    top_k: int = 3,
    use_llm: bool = False,
    force_llm: bool = False,
) -> ObjectDiscoveryEvalResult:
    context = DiscoveryContext(
        source_app=case.source_app,
        container_id=case.container_id,
        container_type=case.container_type,
        conversation_window=max(1, len(case.rows)),
        visible_object_count=len(case.rows),
        use_llm=use_llm,
    )
    resolution = resolve_content_rows(
        case.goal,
        case.rows,
        source_app=case.source_app,
        container_id=case.container_id,
        container_type=case.container_type,
        context=context,
        world=None,
        force_llm=force_llm,
    )

    predicted_ids = _candidate_ids_from_resolution(resolution, top_k)
    gold_ids = [int(x) for x in case.gold_entity_ids if str(x).strip()]
    gold_set = set(gold_ids)
    pred_set = set(predicted_ids)
    tp = len(gold_set & pred_set)
    precision = tp / max(1, len(pred_set))
    recall = tp / max(1, len(gold_set))
    f1 = _f1(precision, recall)
    selected_entity_id = _selected_entity_id(resolution)
    top1_correct = bool(selected_entity_id is not None and selected_entity_id in gold_set)

    return ObjectDiscoveryEvalResult(
        case_id=case.case_id,
        description=case.description,
        top_k=top_k,
        gold_entity_ids=gold_ids,
        predicted_entity_ids=predicted_ids,
        selected_entity_id=selected_entity_id,
        top1_correct=top1_correct,
        candidate_precision_at_k=precision,
        candidate_recall_at_k=recall,
        candidate_f1_at_k=f1,
        confidence=float(getattr(resolution, "confidence", 0.0) or 0.0),
        status=str(getattr(resolution, "status", "") or ""),
        supporting_evidence=[str(x) for x in (getattr(resolution, "evidence", None) or []) if str(x)],
        next_information_actions=[
            str(x) for x in (getattr(resolution, "next_information_actions", None) or []) if str(x)
        ],
        selected_text=str(getattr(resolution, "selected_object_text", "") or ""),
        raw=_json_safe(getattr(resolution, "raw", {}) or {}),
    )


def run_object_discovery_eval(
    cases: Optional[Sequence[ObjectDiscoveryEvalCase]] = None,
    *,
    top_k: int = 3,
    use_llm: bool = False,
    force_llm: bool = False,
) -> ObjectDiscoveryEvalSummary:
    cases = list(cases or build_synthetic_cases())
    results: List[ObjectDiscoveryEvalResult] = []
    tp_total = 0
    pred_total = 0
    gold_total = 0
    top1_hits = 0
    precisions: List[float] = []
    recalls: List[float] = []
    f1s: List[float] = []
    notes: List[str] = []

    for case in cases:
        result = evaluate_case(case, top_k=top_k, use_llm=use_llm, force_llm=force_llm)
        results.append(result)
        gold_set = set(result.gold_entity_ids)
        pred_set = set(result.predicted_entity_ids)
        tp = len(gold_set & pred_set)
        tp_total += tp
        pred_total += len(pred_set)
        gold_total += len(gold_set)
        top1_hits += 1 if result.top1_correct else 0
        precisions.append(result.candidate_precision_at_k)
        recalls.append(result.candidate_recall_at_k)
        f1s.append(result.candidate_f1_at_k)
        if not result.top1_correct:
            notes.append(f"{case.case_id}: top1 missed gold={sorted(gold_set)} predicted={result.predicted_entity_ids}")
        if not gold_set & pred_set:
            notes.append(f"{case.case_id}: zero recall@{top_k}")

    micro_precision = tp_total / max(1, pred_total)
    micro_recall = tp_total / max(1, gold_total)
    micro_f1 = _f1(micro_precision, micro_recall)
    macro_precision = sum(precisions) / max(1, len(precisions))
    macro_recall = sum(recalls) / max(1, len(recalls))
    macro_f1 = sum(f1s) / max(1, len(f1s))

    return ObjectDiscoveryEvalSummary(
        case_count=len(results),
        top_k=top_k,
        top1_accuracy=top1_hits / max(1, len(results)),
        micro_candidate_precision_at_k=micro_precision,
        micro_candidate_recall_at_k=micro_recall,
        micro_candidate_f1_at_k=micro_f1,
        macro_candidate_precision_at_k=macro_precision,
        macro_candidate_recall_at_k=macro_recall,
        macro_candidate_f1_at_k=macro_f1,
        total_gold_entities=gold_total,
        total_predicted_entities=pred_total,
        total_true_positive_entities=tp_total,
        cases=results,
        notes=notes,
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic object-discovery precision/recall eval")
    parser.add_argument("--top-k", type=int, default=3, help="Number of ranked candidates to evaluate")
    parser.add_argument("--use-llm", action="store_true", help="Allow the discovery core to rerank via LLM")
    parser.add_argument(
        "--force-llm",
        action="store_true",
        help="Force the LLM rerank path on every case (useful for provider smoke tests)",
    )
    parser.add_argument("--case", action="append", default=[], help="Run only the named case(s)")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args(argv)

    cases = build_synthetic_cases()
    if args.case:
        wanted = {str(x).strip() for x in args.case if str(x).strip()}
        cases = [case for case in cases if case.case_id in wanted]
    summary = run_object_discovery_eval(
        cases,
        top_k=max(1, int(args.top_k or 3)),
        use_llm=bool(args.use_llm),
        force_llm=bool(args.force_llm),
    )
    payload = summary.to_dict()
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
