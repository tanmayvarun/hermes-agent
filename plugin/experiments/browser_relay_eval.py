"""Browser-backed assistant relay evals.

This harness measures two things separately:

1. whether a browser-backed chat service stays on a multi-turn conversation
   path without losing context; and
2. whether the follow-up question generator can synthesize a natural next
   user prompt from the prior answer, using another model.

The runner is intentionally pluggable. Production computer-use drivers can
provide a live invoker later; tests can replay recorded transcripts or inject a
fake runner. The eval itself stays generic and conversation-shaped.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.auxiliary_client import call_llm
from plugin.experiments.model_benchmark import ModelCandidateSpec


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


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


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def _extract_text(response: Any) -> str:
    if isinstance(response, str):
        return response.strip()
    if isinstance(response, dict):
        for key in ("content", "output_text", "text", "answer", "response"):
            val = response.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
    return _clean_text(response)


def _parse_json_object(text: str) -> Dict[str, Any]:
    raw = _clean_text(text)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _prompt_tokens(text: str) -> set[str]:
    tokens = set()
    for token in _norm(text).replace("/", " ").replace("-", " ").split():
        if len(token) >= 4:
            tokens.add(token)
    return tokens


def _score_overlap(text: str, terms: Sequence[str]) -> float:
    cleaned_terms = [_norm(term) for term in terms if _norm(term)]
    if not cleaned_terms:
        return 1.0
    blob = _norm(text)
    hits = sum(1 for term in cleaned_terms if term in blob)
    return hits / max(1, len(cleaned_terms))


@dataclass
class BrowserRelayCandidateSpec:
    """A browser-backed assistant relay candidate.

    ``service_name`` identifies the actual assistant surface being used
    (e.g. ``chatgpt`` or ``google``); ``transport_provider`` identifies the
    browser transport layer (e.g. Browser Use, Browserbase, or a future local
    browser relay).
    """

    name: str
    service_name: str
    transport_provider: str = "browser-use"
    background_safe: bool = True
    requires_human_cta: bool = False
    auth_mode: str = "browser_session"
    notes: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BrowserRelayCandidateSpec":
        name = _clean_text(data.get("name") or data.get("id") or "")
        service_name = _clean_text(data.get("service_name") or data.get("service") or "")
        transport_provider = _clean_text(
            data.get("transport_provider") or data.get("browser_provider") or "browser-use"
        )
        if not name:
            name = f"{service_name or transport_provider}:{transport_provider}"
        return cls(
            name=name,
            service_name=service_name or "unknown",
            transport_provider=transport_provider or "browser-use",
            background_safe=bool(data.get("background_safe", True)),
            requires_human_cta=bool(data.get("requires_human_cta", False)),
            auth_mode=_clean_text(data.get("auth_mode") or "browser_session"),
            notes=_clean_text(data.get("notes") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BrowserRelayCase:
    """One multi-turn chat relay case."""

    case_id: str
    service_name: str
    objective: str
    seed_prompt: str
    expected_terms: List[str] = field(default_factory=list)
    forbidden_terms: List[str] = field(default_factory=list)
    max_turns: int = 3
    description: str = ""
    notes: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BrowserRelayCase":
        return cls(
            case_id=_clean_text(data.get("case_id") or data.get("id") or ""),
            service_name=_clean_text(data.get("service_name") or data.get("service") or "chatgpt"),
            objective=_clean_text(data.get("objective") or ""),
            seed_prompt=_clean_text(data.get("seed_prompt") or data.get("prompt") or ""),
            expected_terms=[_clean_text(x) for x in data.get("expected_terms") or [] if _clean_text(x)],
            forbidden_terms=[_clean_text(x) for x in data.get("forbidden_terms") or [] if _clean_text(x)],
            max_turns=int(data.get("max_turns") or 3),
            description=_clean_text(data.get("description") or ""),
            notes=_clean_text(data.get("notes") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def initial_messages(self) -> List[Dict[str, str]]:
        return [{"role": "user", "content": self.seed_prompt}]


@dataclass
class BrowserRelayTurnResult:
    turn_index: int
    user_prompt: str
    assistant_response: str
    followup_prompt: str = ""
    assistant_overlap_score: float = 0.0
    followup_overlap_score: float = 0.0
    used_background_mode: bool = True
    foreground_focus_changes: int = 0
    browser_service_used: str = ""
    transport_provider_used: str = ""
    requires_human_cta: bool = False
    notes: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "user_prompt": self.user_prompt,
            "assistant_response": self.assistant_response,
            "followup_prompt": self.followup_prompt,
            "assistant_overlap_score": round(float(self.assistant_overlap_score or 0.0), 4),
            "followup_overlap_score": round(float(self.followup_overlap_score or 0.0), 4),
            "used_background_mode": bool(self.used_background_mode),
            "foreground_focus_changes": int(self.foreground_focus_changes),
            "browser_service_used": self.browser_service_used,
            "transport_provider_used": self.transport_provider_used,
            "requires_human_cta": bool(self.requires_human_cta),
            "notes": self.notes,
            "raw": _json_safe(self.raw),
        }


@dataclass
class BrowserRelayCaseResult:
    case_id: str
    service_name: str
    candidate_name: str
    transport_provider: str
    turn_count: int
    max_turns: int
    mean_assistant_overlap: float
    mean_followup_overlap: float
    background_safe_rate: float
    foreground_focus_changes: int
    human_cta_rate: float
    used_expected_service: bool
    completed: bool
    final_assistant_response: str = ""
    turn_results: List[BrowserRelayTurnResult] = field(default_factory=list)
    notes: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def score(self) -> float:
        parts = [
            self.mean_assistant_overlap,
            self.mean_followup_overlap,
            self.background_safe_rate,
            1.0 if self.used_expected_service else 0.0,
            1.0 if self.completed else 0.0,
        ]
        return sum(parts) / len(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "service_name": self.service_name,
            "candidate_name": self.candidate_name,
            "transport_provider": self.transport_provider,
            "turn_count": self.turn_count,
            "max_turns": self.max_turns,
            "mean_assistant_overlap": round(float(self.mean_assistant_overlap or 0.0), 4),
            "mean_followup_overlap": round(float(self.mean_followup_overlap or 0.0), 4),
            "background_safe_rate": round(float(self.background_safe_rate or 0.0), 4),
            "foreground_focus_changes": int(self.foreground_focus_changes),
            "human_cta_rate": round(float(self.human_cta_rate or 0.0), 4),
            "used_expected_service": bool(self.used_expected_service),
            "completed": bool(self.completed),
            "score": round(float(self.score or 0.0), 4),
            "final_assistant_response": self.final_assistant_response,
            "turn_results": [turn.to_dict() for turn in self.turn_results],
            "notes": self.notes,
            "raw": _json_safe(self.raw),
        }


@dataclass
class BrowserRelayServiceSummary:
    candidate_name: str
    service_name: str
    transport_provider: str
    case_count: int
    avg_score: float
    avg_assistant_overlap: float
    avg_followup_overlap: float
    background_safe_rate: float
    foreground_focus_changes: float
    human_cta_rate: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_name": self.candidate_name,
            "service_name": self.service_name,
            "transport_provider": self.transport_provider,
            "case_count": self.case_count,
            "avg_score": round(float(self.avg_score or 0.0), 4),
            "avg_assistant_overlap": round(float(self.avg_assistant_overlap or 0.0), 4),
            "avg_followup_overlap": round(float(self.avg_followup_overlap or 0.0), 4),
            "background_safe_rate": round(float(self.background_safe_rate or 0.0), 4),
            "foreground_focus_changes": round(float(self.foreground_focus_changes or 0.0), 4),
            "human_cta_rate": round(float(self.human_cta_rate or 0.0), 4),
        }


@dataclass
class BrowserRelayEvalReport:
    case_count: int
    candidates: List[BrowserRelayCandidateSpec]
    cases: List[BrowserRelayCase]
    case_results: List[BrowserRelayCaseResult]
    service_summaries: List[BrowserRelayServiceSummary]
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_count": self.case_count,
            "candidates": [c.to_dict() for c in self.candidates],
            "cases": [c.to_dict() for c in self.cases],
            "case_results": [r.to_dict() for r in self.case_results],
            "service_summaries": [s.to_dict() for s in self.service_summaries],
            "notes": list(self.notes),
        }


def build_default_candidates() -> List[BrowserRelayCandidateSpec]:
    return [
        BrowserRelayCandidateSpec(
            name="chatgpt-browser",
            service_name="chatgpt",
            transport_provider="browser-use",
            background_safe=True,
            requires_human_cta=False,
            auth_mode="browser_session",
            notes="default ChatGPT relay candidate",
        ),
        BrowserRelayCandidateSpec(
            name="google-browser",
            service_name="google",
            transport_provider="browser-use",
            background_safe=True,
            requires_human_cta=False,
            auth_mode="browser_session",
            notes="default Google relay candidate",
        ),
    ]


def build_default_cases() -> List[BrowserRelayCase]:
    return [
        BrowserRelayCase(
            case_id="chatgpt_followup_clarification",
            service_name="chatgpt",
            objective="Hold a natural multi-turn conversation and ask a useful follow-up that depends on the previous answer.",
            seed_prompt="I need a concise explanation of how to share a Google Drive file with view-only access.",
            expected_terms=["share", "drive", "view", "access"],
            forbidden_terms=["irrelevant", "call"],
            max_turns=3,
            description="ChatGPT relay should stay on task and keep the follow-up grounded in the prior answer.",
        ),
        BrowserRelayCase(
            case_id="chatgpt_followup_refinement",
            service_name="chatgpt",
            objective="Refine a request based on the prior answer and keep the conversation coherent.",
            seed_prompt="I want to clean up my inbox without deleting anything important.",
            expected_terms=["inbox", "archive", "important", "mail"],
            forbidden_terms=["call", "video"],
            max_turns=3,
            description="ChatGPT relay should keep contextual memory across turn 2 and 3.",
        ),
        BrowserRelayCase(
            case_id="google_followup_clarification",
            service_name="google",
            objective="Ask the next best clarifying question after a helpful answer from the browser relay.",
            seed_prompt="What is the quickest way to compare two PDF documents for differences?",
            expected_terms=["compare", "pdf", "difference", "quickest"],
            forbidden_terms=["call", "payment"],
            max_turns=3,
            description="Google relay should preserve the comparison task and not drift to unrelated actions.",
        ),
        BrowserRelayCase(
            case_id="google_followup_refinement",
            service_name="google",
            objective="Use the prior answer to ask a narrowing follow-up that would be natural in a real conversation.",
            seed_prompt="How can I find the best route to a meeting while avoiding toll roads?",
            expected_terms=["route", "meeting", "toll", "roads"],
            forbidden_terms=["call", "video"],
            max_turns=3,
            description="Google relay should keep the follow-up tied to route planning.",
        ),
    ]


def load_candidates(source: str | Path | None) -> List[BrowserRelayCandidateSpec]:
    if not source:
        return []
    path = Path(source).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"browser relay candidate file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("candidates") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return []
    return [BrowserRelayCandidateSpec.from_mapping(item) for item in raw if isinstance(item, Mapping)]


def load_cases(source: str | Path | None) -> List[BrowserRelayCase]:
    if not source:
        return build_default_cases()
    path = Path(source).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"browser relay case file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return build_default_cases()
    return [BrowserRelayCase.from_mapping(item) for item in raw if isinstance(item, Mapping)]


def load_transcript(source: str | Path | None) -> Dict[str, Any]:
    if not source:
        return {}
    path = Path(source).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"browser relay transcript file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _build_recorded_invoker(transcript: Mapping[str, Any]) -> Callable[[BrowserRelayCandidateSpec, BrowserRelayCase, List[Dict[str, str]]], Dict[str, Any]]:
    candidates = transcript.get("candidates") if isinstance(transcript, Mapping) else {}
    if not isinstance(candidates, Mapping):
        candidates = {}

    def _invoke(
        candidate: BrowserRelayCandidateSpec,
        case: BrowserRelayCase,
        conversation: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        candidate_block = candidates.get(candidate.name) or candidates.get(candidate.service_name) or {}
        if not isinstance(candidate_block, Mapping):
            candidate_block = {}
        case_block = candidate_block.get(case.case_id) or candidate_block.get("default") or []
        if not isinstance(case_block, list):
            case_block = []
        turn_index = max(0, (len(conversation) - 1) // 2)
        if turn_index >= len(case_block):
            raise RuntimeError(
                f"recorded transcript missing turn {turn_index} for candidate={candidate.name!r} case={case.case_id!r}"
            )
        entry = case_block[turn_index]
        if not isinstance(entry, Mapping):
            raise RuntimeError(
                f"recorded transcript turn {turn_index} for candidate={candidate.name!r} case={case.case_id!r} is not a mapping"
            )
        return {
            "content": _extract_text(
                entry.get("content")
                or entry.get("assistant_response")
                or entry.get("response")
                or entry
            ),
            "used_background_mode": bool(entry.get("used_background_mode", candidate.background_safe)),
            "foreground_focus_changes": int(entry.get("foreground_focus_changes") or 0),
            "requires_human_cta": bool(entry.get("requires_human_cta", False)),
            "browser_service": _clean_text(entry.get("browser_service") or candidate.service_name),
            "transport_provider": _clean_text(entry.get("transport_provider") or candidate.transport_provider),
            "notes": _clean_text(entry.get("notes") or ""),
            "raw": _json_safe(entry),
        }

    return _invoke


def _default_followup_generator(
    candidate: BrowserRelayCandidateSpec,
    case: BrowserRelayCase,
    conversation: Sequence[Dict[str, str]],
    *,
    followup_model: ModelCandidateSpec | None = None,
    timeout_s: float = 90.0,
) -> Dict[str, Any]:
    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You synthesize the next user follow-up in a natural conversation. "
                "Return ONLY JSON with keys question, stop, reason. "
                "The follow-up should depend on the assistant's last answer and move the goal forward."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "candidate": candidate.to_dict(),
                    "case": case.to_dict(),
                    "conversation": list(conversation),
                    "instruction": "Write the next natural user question only. Stop if the assistant already fully answered the objective.",
                },
                indent=2,
            ),
        },
    ]
    kwargs: Dict[str, Any] = {
        "task": "browser_relay_followup",
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 160,
        "timeout": timeout_s,
    }
    if followup_model is not None:
        kwargs.update(
            {
                "provider": followup_model.provider,
                "model": followup_model.model or None,
                "base_url": followup_model.base_url or None,
                "api_key": followup_model.api_key or None,
                "api_mode": followup_model.api_mode or None,
            }
        )
    response = call_llm(**kwargs)
    text = _extract_text(response)
    payload = _parse_json_object(text)
    question = _clean_text(payload.get("question") or "")
    stop = bool(payload.get("stop", False))
    reason = _clean_text(payload.get("reason") or "")
    if not question and not stop:
        last_answer = _clean_text(conversation[-1]["content"]) if conversation else ""
        if last_answer:
            question = f"Can you clarify the part about {last_answer[:60]}?"
        else:
            question = "Can you expand on that?"
    return {
        "question": question,
        "stop": stop,
        "reason": reason,
        "raw": payload if payload else {"text": text},
    }


def _score_turn(case: BrowserRelayCase, assistant_text: str, followup_text: str) -> Tuple[float, float]:
    assistant_score = _score_overlap(assistant_text, case.expected_terms)
    if case.forbidden_terms and any(term and _norm(term) in _norm(assistant_text) for term in case.forbidden_terms):
        assistant_score *= 0.5
    followup_tokens = _prompt_tokens(followup_text)
    assistant_tokens = _prompt_tokens(assistant_text)
    shared = len(followup_tokens & assistant_tokens)
    followup_score = 0.0
    if followup_text:
        followup_score = min(
            1.0,
            0.5 * _score_overlap(followup_text, case.expected_terms)
            + 0.5 * (shared / max(1, len(followup_tokens))),
        )
        if "?" not in followup_text:
            followup_score *= 0.8
    return assistant_score, followup_score


def run_browser_relay_eval(
    candidates: Sequence[BrowserRelayCandidateSpec],
    *,
    cases: Sequence[BrowserRelayCase] | None = None,
    invoker: Callable[[BrowserRelayCandidateSpec, BrowserRelayCase, List[Dict[str, str]]], Dict[str, Any]] | None = None,
    followup_model: ModelCandidateSpec | None = None,
    followup_generator: Callable[[BrowserRelayCandidateSpec, BrowserRelayCase, Sequence[Dict[str, str]]], Dict[str, Any]] | None = None,
    max_turns: int | None = None,
) -> BrowserRelayEvalReport:
    cases = list(cases or build_default_cases())
    candidates = list(candidates)
    invoker = invoker or _default_invoker
    followup_generator = followup_generator or (
        lambda candidate, case, conversation: _default_followup_generator(
            candidate,
            case,
            conversation,
            followup_model=followup_model,
        )
    )

    case_results: List[BrowserRelayCaseResult] = []
    notes: List[str] = []
    if followup_model is not None:
        notes.append(f"followup_model={followup_model.name}")

    for candidate in candidates:
        for case in cases:
            if case.service_name and candidate.service_name and _norm(case.service_name) != _norm(candidate.service_name):
                continue

            conversation: List[Dict[str, str]] = [{"role": "user", "content": case.seed_prompt}]
            turn_results: List[BrowserRelayTurnResult] = []
            turn_limit = int(max_turns or case.max_turns or 3)
            completed = False
            used_background_mode = bool(candidate.background_safe)
            foreground_focus_changes = 0
            human_cta_count = 0
            final_assistant_response = ""

            for turn_index in range(turn_limit):
                response = invoker(candidate, case, list(conversation))
                assistant_text = _extract_text(response)
                final_assistant_response = assistant_text
                assistant_score, _ = _score_turn(case, assistant_text, "")

                conversation.append({"role": "assistant", "content": assistant_text})
                generated = followup_generator(candidate, case, list(conversation))
                followup_text = _clean_text(generated.get("question") or "")
                stop = bool(generated.get("stop", False))
                _, followup_score = _score_turn(case, assistant_text, followup_text)
                used_background_mode = used_background_mode and bool(response.get("used_background_mode", candidate.background_safe))
                foreground_focus_changes += int(response.get("foreground_focus_changes") or 0)
                human_cta_count += 1 if bool(response.get("requires_human_cta", False)) else 0

                turn_results.append(
                    BrowserRelayTurnResult(
                        turn_index=turn_index,
                        user_prompt=conversation[-2]["content"] if len(conversation) >= 2 else case.seed_prompt,
                        assistant_response=assistant_text,
                        followup_prompt=followup_text,
                        assistant_overlap_score=assistant_score,
                        followup_overlap_score=followup_score,
                        used_background_mode=bool(response.get("used_background_mode", candidate.background_safe)),
                        foreground_focus_changes=int(response.get("foreground_focus_changes") or 0),
                        browser_service_used=_clean_text(response.get("browser_service") or candidate.service_name),
                        transport_provider_used=_clean_text(response.get("transport_provider") or candidate.transport_provider),
                        requires_human_cta=bool(response.get("requires_human_cta", False)),
                        notes=_clean_text(response.get("notes") or generated.get("reason") or ""),
                        raw={"response": _json_safe(response), "followup": _json_safe(generated)},
                    )
                )

                if stop or not followup_text:
                    completed = bool(stop)
                    break
                conversation.append({"role": "user", "content": followup_text})

            assistant_scores = [turn.assistant_overlap_score for turn in turn_results]
            followup_scores = [turn.followup_overlap_score for turn in turn_results]
            background_rate = sum(1 for turn in turn_results if turn.used_background_mode) / max(1, len(turn_results))
            human_cta_rate = human_cta_count / max(1, len(turn_results))
            case_results.append(
                BrowserRelayCaseResult(
                    case_id=case.case_id,
                    service_name=case.service_name,
                    candidate_name=candidate.name,
                    transport_provider=candidate.transport_provider,
                    turn_count=len(turn_results),
                    max_turns=turn_limit,
                    mean_assistant_overlap=statistics.fmean(assistant_scores) if assistant_scores else 0.0,
                    mean_followup_overlap=statistics.fmean(followup_scores) if followup_scores else 0.0,
                    background_safe_rate=background_rate,
                    foreground_focus_changes=foreground_focus_changes,
                    human_cta_rate=human_cta_rate,
                    used_expected_service=_norm(candidate.service_name) == _norm(case.service_name),
                    completed=completed,
                    final_assistant_response=final_assistant_response,
                    turn_results=turn_results,
                    notes=case.notes,
                )
            )

    service_summaries: List[BrowserRelayServiceSummary] = []
    grouped: Dict[str, List[BrowserRelayCaseResult]] = {}
    for result in case_results:
        grouped.setdefault(result.candidate_name, []).append(result)

    for candidate in candidates:
        subset = grouped.get(candidate.name, [])
        if not subset:
            continue
        service_summaries.append(
            BrowserRelayServiceSummary(
                candidate_name=candidate.name,
                service_name=candidate.service_name,
                transport_provider=candidate.transport_provider,
                case_count=len(subset),
                avg_score=statistics.fmean([item.score for item in subset]),
                avg_assistant_overlap=statistics.fmean([item.mean_assistant_overlap for item in subset]),
                avg_followup_overlap=statistics.fmean([item.mean_followup_overlap for item in subset]),
                background_safe_rate=statistics.fmean([item.background_safe_rate for item in subset]),
                foreground_focus_changes=statistics.fmean([float(item.foreground_focus_changes) for item in subset]),
                human_cta_rate=statistics.fmean([item.human_cta_rate for item in subset]),
            )
        )

    return BrowserRelayEvalReport(
        case_count=len(case_results),
        candidates=list(candidates),
        cases=cases,
        case_results=case_results,
        service_summaries=service_summaries,
        notes=notes,
    )


def _default_invoker(
    candidate: BrowserRelayCandidateSpec,
    case: BrowserRelayCase,
    conversation: List[Dict[str, str]],
) -> Dict[str, Any]:
    raise RuntimeError(
        "browser relay eval needs a live invoker or a recorded transcript; "
        "wire a computer-use runner into this callable before using the CLI"
    )


def _print_human_summary(report: BrowserRelayEvalReport) -> None:
    print(
        f"cases={report.case_count} candidates={len(report.candidates)} "
        f"service_summaries={len(report.service_summaries)}"
    )
    if report.notes:
        print("notes:", "; ".join(report.notes))
    print()
    print("Leaderboard")
    print(f"{'candidate':<28} {'service':<12} {'transport':<14} {'score':>8} {'cases':>5}")
    print("-" * 72)
    for summary in sorted(report.service_summaries, key=lambda s: (-s.avg_score, s.candidate_name.lower())):
        print(
            f"{summary.candidate_name:<28} {summary.service_name:<12} {summary.transport_provider:<14} "
            f"{summary.avg_score:>8.2%} {summary.case_count:>5}"
        )
    print()
    print("Per-case")
    print(f"{'case':<34} {'candidate':<24} {'score':>8} {'bg':>6} {'cta':>6} {'focus':>6}")
    print("-" * 86)
    for result in sorted(report.case_results, key=lambda r: (r.candidate_name.lower(), r.case_id.lower())):
        print(
            f"{result.case_id:<34} {result.candidate_name:<24} {result.score:>8.2%} "
            f"{result.background_safe_rate:>6.0%} {result.human_cta_rate:>6.0%} {result.foreground_focus_changes:>6}"
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark browser-backed assistant relays")
    parser.add_argument(
        "--candidate-file",
        default="",
        help="Path to a JSON file with browser relay candidate specs.",
    )
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Inline JSON candidate spec (repeatable).",
    )
    parser.add_argument(
        "--case-file",
        default="",
        help="Path to a JSON file with browser relay cases.",
    )
    parser.add_argument(
        "--followup-model",
        default="",
        help="Optional JSON model candidate spec used to synthesize follow-up questions.",
    )
    parser.add_argument(
        "--trace-file",
        default="",
        help="Recorded transcript JSON to replay instead of using a live browser runner.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="Optional global cap on turns per case.",
    )
    parser.add_argument("--report", default="", help="Optional path to write JSON output.")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args(argv)

    candidates = load_candidates(args.candidate_file)
    for raw_item in args.candidate or []:
        payload = json.loads(raw_item)
        if not isinstance(payload, dict):
            raise ValueError(f"invalid --candidate payload: {raw_item!r}")
        candidates.append(BrowserRelayCandidateSpec.from_mapping(payload))
    if not candidates:
        candidates = build_default_candidates()

    cases = load_cases(args.case_file)
    followup_model = None
    if args.followup_model:
        payload = json.loads(args.followup_model)
        if not isinstance(payload, dict):
            raise ValueError("--followup-model must be a JSON object")
        followup_model = ModelCandidateSpec.from_mapping(payload)

    transcript = load_transcript(args.trace_file)
    invoker = None
    notes: List[str] = []
    if transcript:
        invoker = _build_recorded_invoker(transcript)
        notes.append(f"replayed transcript={Path(args.trace_file).expanduser()}")

    report = run_browser_relay_eval(
        candidates,
        cases=cases,
        invoker=invoker,
        followup_model=followup_model,
        max_turns=args.max_turns,
    )
    if notes:
        report.notes.extend(notes)
    payload = report.to_dict()
    if args.report:
        path = Path(args.report).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        _print_human_summary(report)
        print()
        print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
