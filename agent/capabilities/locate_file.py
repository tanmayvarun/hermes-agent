"""LocateFileCapability — stateful find-file strategy above search primitives.

Internal loop (deterministic-first)::

  OBSERVE → parse attributes
  UPDATE STATE → staged filename / scoped / content search
  ASSESS → confidence threshold / escalate / optional LLM rank
  RETURN CapabilityResult

The LLM is not asked whether to re-run the same grep; code forbids that.
Optional judgment (rank ambiguous shortlists) is injected via ``judge_fn``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from agent.capabilities.base import Capability, CapabilityContext, CapabilityResult

logger = logging.getLogger(__name__)

CONFIDENCE_STOP = 0.90
AMBIGUOUS_LOW = 0.55
AMBIGUOUS_HIGH = 0.89

JudgeFn = Callable[[str, List[Dict[str, Any]]], Optional[Dict[str, Any]]]

_LOCATE_VERB_RE = re.compile(
    r"\b(find|locate|where\s+is|show\s+me|get\s+me|open)\b",
    re.I,
)
_LOCATE_OBJECT_RE = re.compile(
    r"\b(file|pdf|docx?|xlsx?|brochure|invoice|quotation|spec(?:s|ification)?s?|"
    r"datasheet|manual|document)\b",
    re.I,
)
_CODING_BLOCK_RE = re.compile(
    r"\b(bug|refactor|pytest|implement|compile|lint|pull request|pr\b)\b",
    re.I,
)


@dataclass
class ParsedLocateQuery:
    """Likely attributes extracted from a find-file objective."""

    brand: Optional[str] = None
    power: Optional[str] = None
    document_type: Optional[str] = None
    version: Optional[str] = None
    tokens: List[str] = field(default_factory=list)
    extensions: List[str] = field(default_factory=list)


def is_locate_intent(message: str) -> bool:
    """True when the user turn looks like locate-and-show-file."""
    text = (message or "").strip()
    if not text or len(text) > 2000:
        return False
    if _CODING_BLOCK_RE.search(text):
        return False
    if not _LOCATE_VERB_RE.search(text):
        return False
    # Verb alone is enough for short queries; prefer object cue when present.
    if _LOCATE_OBJECT_RE.search(text):
        return True
    # "Find Plugin 3.3kW Technical Specifications V3" (no explicit "file")
    if re.search(r"\b(v\d+|specs?|specification|brochure|invoice)\b", text, re.I):
        return True
    # Short find queries with a distinctive noun phrase
    words = re.findall(r"[A-Za-z0-9.]+", text)
    return len(words) >= 3


def parse_locate_query(objective: str) -> ParsedLocateQuery:
    from tools.locate_file import infer_extensions, tokenize_query

    tokens = tokenize_query(objective)
    exts = infer_extensions(objective)
    brand = next((t for t in tokens if t.isalpha() and len(t) >= 4), None)
    power = next((t for t in tokens if "kw" in t), None)
    version = next((t for t in tokens if re.fullmatch(r"v\d+", t)), None)
    doc_type = None
    joined = " ".join(tokens)
    for hint in (
        "specifications",
        "specification",
        "specs",
        "brochure",
        "invoice",
        "quotation",
        "datasheet",
        "manual",
    ):
        if hint in joined or hint in (objective or "").lower():
            doc_type = hint
            break
    return ParsedLocateQuery(
        brand=brand,
        power=power,
        document_type=doc_type,
        version=version,
        tokens=tokens,
        extensions=exts,
    )


class LocateFileCapability(Capability):
    name = "locate_file"
    description = (
        "Locate a file from a natural-language or filename-ish query using a "
        "staged deterministic search (filename → scoped dirs → content), with "
        "optional LLM ranking only when candidates are ambiguous."
    )
    required_tools = ["search_files", "read_file"]

    def __init__(self, judge_fn: Optional[JudgeFn] = None) -> None:
        self.judge_fn = judge_fn

    def execute(self, ctx: CapabilityContext) -> CapabilityResult:
        objective = (ctx.objective or "").strip()
        observations: List[Dict[str, Any]] = []
        attempts: List[Dict[str, Any]] = []
        evidence: List[Dict[str, Any]] = []

        if not objective:
            return CapabilityResult(
                status="failed",
                capability=self.name,
                message="objective is required",
                confidence=0.0,
            )

        # OBSERVE — parse attributes
        parsed = parse_locate_query(objective)
        observations.append(
            {
                "step": "parse",
                "brand": parsed.brand,
                "power": parsed.power,
                "document_type": parsed.document_type,
                "version": parsed.version,
                "tokens": parsed.tokens,
                "extensions": parsed.extensions,
            }
        )

        from tools.locate_file import locate_file as run_staged

        roots = ctx.extras.get("roots")
        extensions = ctx.extras.get("extensions") or parsed.extensions or None
        max_candidates = int(ctx.extras.get("max_candidates") or 5)
        search_fn = ctx.extras.get("search_fn")
        task_id = ctx.task_id or ctx.session_id or "default"

        # UPDATE STATE — deterministic staged search
        attempts.append({"action": "staged_search", "query": objective})
        engine = run_staged(
            query=objective,
            roots=roots,
            extensions=extensions,
            max_candidates=max_candidates,
            task_id=task_id,
            search_fn=search_fn,
        )
        attempts.append(
            {
                "action": "staged_search_result",
                "stages_run": engine.get("stages_run"),
                "stopped_reason": engine.get("stopped_reason"),
                "internal_searches": engine.get("internal_searches"),
                "candidate_count": len(engine.get("candidates") or []),
            }
        )

        candidates = list(engine.get("candidates") or [])
        for c in candidates[:5]:
            evidence.append(
                {
                    "path": c.get("path"),
                    "confidence": c.get("confidence"),
                    "stage": c.get("stage"),
                    "reason": c.get("reason"),
                }
            )

        # ASSESS
        top = candidates[0] if candidates else None
        top_conf = float(top["confidence"]) if top else 0.0

        if top and top_conf >= CONFIDENCE_STOP:
            return CapabilityResult(
                status="success",
                capability=self.name,
                output={
                    "query": objective,
                    "parsed": {
                        "brand": parsed.brand,
                        "power": parsed.power,
                        "document_type": parsed.document_type,
                        "version": parsed.version,
                    },
                    "candidates": candidates,
                    "stages_run": engine.get("stages_run"),
                    "stopped_reason": engine.get("stopped_reason"),
                    "already_completed": engine.get("already_completed", False),
                    "internal_searches": engine.get("internal_searches"),
                },
                confidence=top_conf,
                evidence=evidence,
                observations=observations,
                attempts=attempts,
                artifacts=[top["path"]],
                message="Strong filename/path match; selected top candidate.",
            )

        # Ambiguous shortlist → optional LLM judgment
        ambiguous = [
            c
            for c in candidates
            if AMBIGUOUS_LOW <= float(c.get("confidence") or 0) <= AMBIGUOUS_HIGH
        ]
        if len(ambiguous) >= 2 or (top and AMBIGUOUS_LOW <= top_conf < CONFIDENCE_STOP):
            judgment = self._judge(objective, candidates[:5])
            if judgment:
                observations.append({"step": "llm_judgment", **judgment})
                chosen = judgment.get("path")
                if chosen:
                    # Reorder candidates
                    ordered = [c for c in candidates if c.get("path") == chosen]
                    ordered.extend(c for c in candidates if c.get("path") != chosen)
                    candidates = ordered
                    top = candidates[0]
                    top_conf = max(
                        top_conf,
                        float(judgment.get("confidence") or top_conf),
                    )
                    evidence.append(
                        {
                            "path": chosen,
                            "confidence": top_conf,
                            "stage": "llm_judgment",
                            "reason": judgment.get("reason") or "llm rank",
                        }
                    )
                    if top_conf >= CONFIDENCE_STOP or judgment.get("select"):
                        return CapabilityResult(
                            status="success",
                            capability=self.name,
                            output={
                                "query": objective,
                                "parsed": {
                                    "brand": parsed.brand,
                                    "power": parsed.power,
                                    "document_type": parsed.document_type,
                                    "version": parsed.version,
                                },
                                "candidates": candidates,
                                "stages_run": list(engine.get("stages_run") or [])
                                + ["llm_judgment"],
                                "stopped_reason": "llm_judgment",
                                "internal_searches": engine.get("internal_searches"),
                            },
                            confidence=top_conf,
                            evidence=evidence,
                            observations=observations,
                            attempts=attempts,
                            artifacts=[chosen],
                            message=judgment.get("reason")
                            or "Selected via LLM judgment among ambiguous candidates.",
                        )

        if top:
            return CapabilityResult(
                status="partial",
                capability=self.name,
                output={
                    "query": objective,
                    "parsed": {
                        "brand": parsed.brand,
                        "power": parsed.power,
                        "document_type": parsed.document_type,
                        "version": parsed.version,
                    },
                    "candidates": candidates,
                    "stages_run": engine.get("stages_run"),
                    "stopped_reason": engine.get("stopped_reason"),
                    "internal_searches": engine.get("internal_searches"),
                },
                confidence=top_conf,
                evidence=evidence,
                observations=observations,
                attempts=attempts,
                artifacts=[top["path"]],
                unresolved_questions=[
                    "Top candidate is below confidence threshold; confirm before opening."
                ],
                message="Candidates found but confidence is below stop threshold.",
            )

        return CapabilityResult(
            status="failed",
            capability=self.name,
            output={
                "query": objective,
                "parsed": {
                    "brand": parsed.brand,
                    "power": parsed.power,
                    "document_type": parsed.document_type,
                    "version": parsed.version,
                },
                "candidates": [],
                "stages_run": engine.get("stages_run"),
                "stopped_reason": engine.get("stopped_reason") or "not_found",
                "internal_searches": engine.get("internal_searches"),
            },
            confidence=0.0,
            evidence=evidence,
            observations=observations,
            attempts=attempts,
            unresolved_questions=["No matching file found with staged search."],
            message="No candidates found.",
        )

    def _judge(
        self, objective: str, candidates: Sequence[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if self.judge_fn is not None:
            try:
                return self.judge_fn(objective, list(candidates))
            except Exception:
                logger.debug("locate_file judge_fn failed", exc_info=True)
                return None
        # Optional ambient LLM judge (off by default — avoid surprise API cost)
        import os

        if os.environ.get("HERMES_CAPABILITY_LLM_JUDGE", "").lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return None
        try:
            from agent.auxiliary_client import call_llm

            prompt = (
                "Pick the best file path for the user objective. "
                "Reply JSON only: {\"path\": \"...\", \"confidence\": 0-1, "
                "\"select\": true/false, \"reason\": \"...\"}.\n\n"
                f"Objective: {objective}\n"
                f"Candidates: {json.dumps(list(candidates), ensure_ascii=False)}"
            )
            resp = call_llm(
                task="mcp",
                messages=[
                    {
                        "role": "system",
                        "content": "You rank filesystem candidates. JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=300,
            )
            content = (
                resp.choices[0].message.content
                if resp and getattr(resp, "choices", None)
                else ""
            )
            if not content:
                return None
            # Extract JSON object
            start = content.find("{")
            end = content.rfind("}")
            if start < 0 or end <= start:
                return None
            data = json.loads(content[start : end + 1])
            if not isinstance(data, dict) or not data.get("path"):
                return None
            return data
        except Exception:
            logger.debug("locate_file LLM judge unavailable", exc_info=True)
            return None

    def to_tool_payload(self, result: CapabilityResult) -> Dict[str, Any]:
        """Shape returned by the locate_file tool (backward compatible + richer)."""
        out = result.output if isinstance(result.output, dict) else {}
        return {
            "success": result.status in {"success", "partial"},
            "capability": self.name,
            "status": result.status,
            "query": out.get("query"),
            "parsed": out.get("parsed"),
            "stages_run": out.get("stages_run") or [],
            "stopped_reason": out.get("stopped_reason") or result.message,
            "already_completed": out.get("already_completed", False),
            "internal_searches": out.get("internal_searches"),
            "confidence": round(result.confidence, 3),
            "candidates": out.get("candidates") or [],
            "artifacts": list(result.artifacts),
            "evidence": list(result.evidence),
            "observations": list(result.observations),
            "attempts": list(result.attempts),
            "unresolved_questions": list(result.unresolved_questions),
            "message": result.message,
        }
