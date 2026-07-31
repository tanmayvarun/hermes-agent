"""Deterministic locate_file engine — staged filesystem search.

The LLM expresses find-intent; this module owns strategy:

  filename → scoped_dirs → content

with confidence-based early stop and per-turn stage caching so the same
query does not re-run completed stages.
"""

from __future__ import annotations

import json
import os
import re
import threading
from fnmatch import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

CONFIDENCE_STOP = 0.90
MAX_INTERNAL_SEARCHES = 6
DEFAULT_MAX_CANDIDATES = 5

DEFAULT_ROOTS: Tuple[str, ...] = (
    ".",
    "~/Downloads",
    "~/Desktop",
    "~/Documents",
    "~",
)

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "file",
        "files",
        "find",
        "locate",
        "show",
        "open",
        "get",
        "please",
        "me",
        "my",
        "latest",
        "and",
        "or",
        "of",
        "for",
        "to",
        "in",
        "on",
        "with",
        "document",
        "doc",
        "download",
        "downloads",
        "folder",
    }
)

_EXT_HINTS = {
    "pdf": [".pdf"],
    "docx": [".docx", ".doc"],
    "xlsx": [".xlsx", ".xls", ".csv"],
    "pptx": [".pptx", ".ppt"],
    "md": [".md", ".markdown"],
    "txt": [".txt"],
    "png": [".png", ".jpg", ".jpeg", ".webp"],
}

_VERSION_RE = re.compile(r"\bv\.?\s*(\d+)\b|\bv(\d+)\b", re.I)
_KW_RE = re.compile(r"(\d+(?:\.\d+)?)\s*k\s*w", re.I)

SearchFn = Callable[..., Any]  # returns SearchResult-like or list[str]


@dataclass
class Candidate:
    path: str
    confidence: float
    stage: str
    reason: str


@dataclass
class LocateState:
    stages_run: List[str] = field(default_factory=list)
    candidates: List[Candidate] = field(default_factory=list)
    internal_searches: int = 0
    stopped_reason: str = ""


_lock = threading.Lock()
# (task_id, normalized_query) -> LocateState
_STATE: Dict[Tuple[str, str], LocateState] = {}


def reset_locate_state(task_id: str = "") -> None:
    """Clear cached locate state (tests / new turn)."""
    with _lock:
        if not task_id:
            _STATE.clear()
            return
        keys = [k for k in _STATE if k[0] == task_id]
        for k in keys:
            _STATE.pop(k, None)


def normalize_query(query: str) -> str:
    q = (query or "").strip().lower()
    q = _KW_RE.sub(lambda m: f"{m.group(1)}kw", q)
    q = re.sub(r"\s+", " ", q)
    return q


def tokenize_query(query: str) -> List[str]:
    """Extract meaningful tokens; merge 3.3 kw → 3.3kw."""
    q = normalize_query(query)
    # Keep versions as v3 tokens
    q = _VERSION_RE.sub(lambda m: f" v{m.group(1) or m.group(2)} ", q)
    raw = re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)?", q)
    tokens: List[str] = []
    for t in raw:
        if t in _STOPWORDS:
            continue
        if len(t) == 1 and not t.isdigit():
            continue
        tokens.append(t)
    # Dedupe preserving order
    seen = set()
    out = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def infer_extensions(query: str, explicit: Optional[Sequence[str]] = None) -> List[str]:
    if explicit:
        exts = []
        for e in explicit:
            e = e.strip().lower()
            if not e:
                continue
            if not e.startswith("."):
                e = "." + e
            exts.append(e)
        return exts
    q = (query or "").lower()
    found: List[str] = []
    for hint, exts in _EXT_HINTS.items():
        if re.search(rf"\b{re.escape(hint)}\b", q):
            found.extend(exts)
    if not found and any(
        w in q for w in ("spec", "brochure", "invoice", "quotation", "manual", "datasheet")
    ):
        found = [".pdf", ".docx", ".doc"]
    return found


def build_filename_globs(tokens: Sequence[str], extensions: Sequence[str]) -> List[str]:
    """Build a few compact globs from tokens.

    In practice, broad-but-distinctive globs work better than a fully literal
    token chain for natural-language file requests, so we surface shorter
    high-signal patterns before the exhaustive version.
    """
    if not tokens:
        return ["*"]
    # Prefer substantive tokens (skip tiny ones except versions/kw)
    significant = [t for t in tokens if len(t) >= 3 or t.startswith("v") or "kw" in t]
    if not significant:
        significant = list(tokens)

    globs: List[str] = []
    # Shorter: first + last significant
    if len(significant) >= 2:
        short = f"*{significant[0]}*{significant[-1]}*"
        if extensions:
            for ext in extensions[:2]:
                globs.append(f"{short}{ext}" if short.endswith("*") else f"{short}*{ext}")
        else:
            globs.append(short if short.endswith("*") else short + "*")

    # KW + version if present
    kw = next((t for t in significant if "kw" in t), None)
    ver = next((t for t in significant if re.fullmatch(r"v\d+", t)), None)
    brand = next((t for t in significant if t.isalpha() and len(t) >= 4), None)
    if brand and kw:
        piece = f"*{brand}*{kw}*"
        if ver:
            piece = f"*{brand}*{kw}*{ver}*"
        if extensions:
            for ext in extensions[:2]:
                globs.append(f"{piece}{ext}" if piece.endswith("*") else f"{piece}*{ext}")
        else:
            globs.append(piece)

    # Full token chain
    core = "*".join(significant[:6])
    if extensions:
        for ext in extensions[:3]:
            globs.append(f"*{core}*{ext}")
    else:
        globs.append(f"*{core}*")

    # Dedupe
    seen = set()
    out = []
    for g in globs:
        g2 = re.sub(r"\*+", "*", g)
        if g2 not in seen:
            seen.add(g2)
            out.append(g2)
    return out[:5]


def score_candidate(
    path: str,
    tokens: Sequence[str],
    extensions: Sequence[str],
    *,
    stage: str,
) -> Tuple[float, str]:
    """Return (confidence, reason)."""
    basename = os.path.basename(path)
    name_l = basename.lower()
    # Normalize 3.3 kw style inside names
    name_norm = _KW_RE.sub(lambda m: f"{m.group(1)}kw", name_l)
    name_norm = name_norm.replace(" ", "").replace("_", "").replace("-", "")

    if not tokens:
        return 0.1, "no query tokens"

    def _token_weight(token: str) -> float:
        if re.fullmatch(r"v\d+", token):
            return 1.3
        if "kw" in token:
            return 1.4
        if token in {"technical", "tech", "spec", "specs", "specification", "specifications"}:
            return 1.2
        if token in {"ev", "charger"}:
            return 0.45
        if len(token) <= 2:
            return 0.4
        if len(token) >= 6:
            return 1.1
        return 1.0

    hits = 0
    matched_weight = 0.0
    total_weight = 0.0
    for t in tokens:
        weight = _token_weight(t)
        total_weight += weight
        t_norm = t.replace(" ", "")
        if t_norm in name_norm or t in name_l:
            hits += 1
            matched_weight += weight
    frac = matched_weight / max(total_weight, 1.0)

    score = 0.55 * frac
    reasons = [f"{hits}/{len(tokens)} tokens in name"]

    # Version bonus
    vers = [t for t in tokens if re.fullmatch(r"v\d+", t)]
    if vers and any(v in name_l for v in vers):
        score += 0.15
        reasons.append("version match")

    # Extension bonus
    _, ext = os.path.splitext(name_l)
    if extensions and ext in extensions:
        score += 0.12
        reasons.append(f"ext {ext}")
    elif not extensions and ext in {".pdf", ".docx", ".doc", ".xlsx", ".md", ".txt"}:
        score += 0.05
        reasons.append(f"doc ext {ext}")

    # Document-folder bonus
    path_l = path.replace("\\", "/").lower()
    if any(seg in path_l for seg in ("/downloads", "/desktop", "/documents")):
        score += 0.08
        reasons.append("common doc folder")

    brand_token = next((t for t in tokens if t.isalpha() and len(t) >= 4), "")
    has_brand = bool(brand_token and brand_token in name_l)
    has_power = any("kw" in t and t in name_norm for t in tokens)
    has_spec_family = any(
        t in {"technical", "tech", "spec", "specs", "specification", "specifications"}
        and ("tech" in name_norm or "spec" in name_norm)
        for t in tokens
    )
    if has_brand and has_power and has_spec_family:
        score += 0.22
        reasons.append("brand/power/spec anchor match")

    # Exact-ish: all tokens hit
    if frac >= 1.0:
        score += 0.15
        reasons.append("all tokens")
    elif frac >= 0.8:
        score += 0.08

    # Weak overlap penalty
    if frac < 0.34:
        score *= 0.5
        reasons.append("weak overlap")

    # Stage slight discount for content-only discovery
    if stage == "content" and frac < 0.5:
        score *= 0.85

    score = max(0.0, min(1.0, score))
    return score, " + ".join(reasons)


def _default_roots(roots: Optional[Sequence[str]]) -> List[str]:
    if roots:
        return [str(r) for r in roots if str(r).strip()]
    return list(DEFAULT_ROOTS)


def _prioritize_roots(query: str, roots: Sequence[str]) -> List[str]:
    ordered = [str(r) for r in roots if str(r).strip()]
    q = (query or "").lower()

    preferred: List[str] = []
    if "download" in q:
        preferred.append("~/Downloads")
    if "desktop" in q:
        preferred.append("~/Desktop")
    if "document" in q:
        preferred.append("~/Documents")

    out: List[str] = []
    seen = set()
    for root in preferred + ordered:
        if root not in seen:
            seen.add(root)
            out.append(root)
    return out


def _expand_root(root: str) -> str:
    return os.path.expanduser(root.strip())


def _path_exists(path: str) -> bool:
    try:
        return os.path.exists(path)
    except OSError:
        return False


def _search_files_via_ops(
    file_ops: Any,
    pattern: str,
    path: str,
    *,
    target: str = "files",
    file_glob: Optional[str] = None,
    limit: int = 40,
) -> List[str]:
    result = file_ops.search(
        pattern=pattern,
        path=path,
        target=target,
        file_glob=file_glob,
        limit=limit,
        offset=0,
        output_mode="files_only" if target == "content" else "content",
    )
    if getattr(result, "error", None):
        return []
    paths: List[str] = []
    if getattr(result, "files", None):
        paths.extend(result.files)
    if getattr(result, "matches", None):
        for m in result.matches:
            p = getattr(m, "path", None)
            if p:
                paths.append(p)
    # Dedupe
    seen = set()
    out = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _search_files_pathlib(pattern: str, path: str, limit: int = 40) -> List[str]:
    """Local fallback/filename search without shell (also used in tests).

    Matching is case-insensitive to mirror user expectations for ordinary file
    lookup prompts such as ``3.3kw`` vs ``3.3kW`` on mixed-case filenames.
    """
    root = Path(_expand_root(path))
    if not root.exists():
        return []
    found: List[str] = []
    simple_pat = pattern.replace("**/", "").lower()
    try:
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if fnmatch(p.name.lower(), simple_pat):
                found.append(str(p.resolve()))
                if len(found) >= limit:
                    break
    except (OSError, ValueError):
        return found
    return found


def _get_search_backend(task_id: str, search_fn: Optional[SearchFn]) -> SearchFn:
    if search_fn is not None:
        return search_fn

    def _backend(pattern, path, target="files", file_glob=None, limit=40):
        try:
            from tools.file_tools import _get_file_ops

            ops = _get_file_ops(task_id)
            return _search_files_via_ops(
                ops, pattern, path, target=target, file_glob=file_glob, limit=limit
            )
        except Exception:
            if target == "files":
                return _search_files_pathlib(pattern, path, limit=limit)
            return []

    return _backend


def _merge_candidates(
    existing: List[Candidate],
    paths: Sequence[str],
    tokens: Sequence[str],
    extensions: Sequence[str],
    stage: str,
) -> List[Candidate]:
    by_path = {c.path: c for c in existing}
    for path in paths:
        conf, reason = score_candidate(path, tokens, extensions, stage=stage)
        prev = by_path.get(path)
        if prev is None or conf > prev.confidence:
            by_path[path] = Candidate(
                path=path, confidence=conf, stage=stage, reason=reason
            )
    ranked = sorted(by_path.values(), key=lambda c: c.confidence, reverse=True)
    return ranked


def locate_file(
    query: str,
    roots: Optional[Sequence[str]] = None,
    extensions: Optional[Sequence[str]] = None,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    task_id: str = "default",
    search_fn: Optional[SearchFn] = None,
) -> Dict[str, Any]:
    """Run staged locate; return JSON-serializable result dict."""
    query = (query or "").strip()
    if not query:
        return {
            "success": False,
            "error": "query is required",
            "candidates": [],
            "stages_run": [],
        }

    norm = normalize_query(query)
    key = (task_id or "default", norm)
    tokens = tokenize_query(query)
    exts = infer_extensions(query, extensions)
    root_list = _prioritize_roots(query, _default_roots(roots))
    custom_backend = search_fn is not None
    backend = _get_search_backend(task_id, search_fn)
    max_candidates = max(1, min(int(max_candidates or DEFAULT_MAX_CANDIDATES), 20))

    with _lock:
        state = _STATE.get(key)
        if state is None:
            state = LocateState()
            _STATE[key] = state
        else:
            # Return cache if this query already finished (any stop reason)
            if state.stopped_reason:
                return {
                    "success": True,
                    "query": query,
                    "stages_run": list(state.stages_run),
                    "stopped_reason": state.stopped_reason,
                    "already_completed": True,
                    "internal_searches": state.internal_searches,
                    "candidates": [
                        {
                            "path": c.path,
                            "confidence": round(c.confidence, 3),
                            "stage": c.stage,
                            "reason": c.reason,
                        }
                        for c in state.candidates[:max_candidates]
                    ],
                }

    def run_search(pattern, path, target="files", file_glob=None, limit=40) -> List[str]:
        if state.internal_searches >= MAX_INTERNAL_SEARCHES:
            return []
        backend_path = str(path)
        if backend_path not in (".", "./"):
            backend_path = _expand_root(backend_path)
        # Skip missing roots for real FS; custom backends (tests) always run.
        if not custom_backend and path not in (".",) and not str(path).startswith("./"):
            expanded = _expand_root(str(path))
            if not _path_exists(expanded):
                return []
        state.internal_searches += 1
        try:
            results = list(
                backend(
                    pattern,
                    backend_path,
                    target=target,
                    file_glob=file_glob,
                    limit=limit,
                )
                or []
            )
            if not results and not custom_backend and target == "files":
                return _search_files_pathlib(pattern, backend_path, limit=limit)
            return results
        except TypeError:
            # Simpler test doubles: backend(pattern, path) only
            try:
                results = list(backend(pattern, backend_path) or [])
                if not results and not custom_backend and target == "files":
                    return _search_files_pathlib(pattern, backend_path, limit=limit)
                return results
            except Exception:
                return []
        except Exception:
            return []

    def top_confidence() -> float:
        return state.candidates[0].confidence if state.candidates else 0.0

    stages_order = ["filename", "scoped_dirs", "content"]

    # --- Stage 1: filename ---
    if "filename" not in state.stages_run:
        state.stages_run.append("filename")
        globs = build_filename_globs(tokens, exts)
        # Prefer cwd + common dirs first (skip bare ~ until scoped)
        stage1_roots = []
        for r in root_list:
            if r in ("~", "~/"):
                continue
            stage1_roots.append(r)
        if not stage1_roots:
            stage1_roots = ["."]
        for root in stage1_roots[:4]:
            for glob in globs[:3]:
                paths = run_search(glob, root, target="files", limit=30)
                state.candidates = _merge_candidates(
                    state.candidates, paths, tokens, exts, "filename"
                )
                if top_confidence() >= CONFIDENCE_STOP:
                    break
            if top_confidence() >= CONFIDENCE_STOP:
                break
        if top_confidence() >= CONFIDENCE_STOP:
            state.stopped_reason = "confidence_threshold"
            return _result(query, state, max_candidates)

    # --- Stage 2: scoped dirs (home common + home) ---
    if "scoped_dirs" not in state.stages_run and state.internal_searches < MAX_INTERNAL_SEARCHES:
        state.stages_run.append("scoped_dirs")
        scoped = ["~/Downloads", "~/Desktop", "~/Documents", "~"]
        # Honor caller roots that look like home paths
        for r in root_list:
            if r.startswith("~") and r not in scoped:
                scoped.insert(0, r)
        globs = build_filename_globs(tokens, exts)
        # Broader: also *token* with extension
        if tokens and exts:
            for t in tokens[:3]:
                for ext in exts[:2]:
                    globs.append(f"*{t}*{ext}")
        globs = list(dict.fromkeys(globs))[:6]
        for root in scoped:
            for glob in globs[:3]:
                paths = run_search(glob, root, target="files", limit=40)
                state.candidates = _merge_candidates(
                    state.candidates, paths, tokens, exts, "scoped_dirs"
                )
                if top_confidence() >= CONFIDENCE_STOP:
                    break
            if top_confidence() >= CONFIDENCE_STOP:
                break
        if top_confidence() >= CONFIDENCE_STOP:
            state.stopped_reason = "confidence_threshold"
            return _result(query, state, max_candidates)

    # --- Stage 3: content ---
    if "content" not in state.stages_run and state.internal_searches < MAX_INTERNAL_SEARCHES:
        state.stages_run.append("content")
        # Distinctive phrase: join longest tokens
        content_terms = [t for t in tokens if len(t) >= 3][:4]
        if content_terms:
            # ripgrep pattern: all terms as AND via lookahead is heavy; use
            # the most distinctive single token or simple alternation.
            primary = max(content_terms, key=len)
            pattern = primary
            if len(content_terms) >= 2:
                pattern = "|".join(re.escape(t) for t in content_terms[:3])
            file_glob = None
            if exts:
                # rg --glob supports one; pick primary
                file_glob = f"*{exts[0]}"
            content_roots = [".", "~/Downloads", "~/Documents", "~/Desktop"]
            for root in content_roots:
                paths = run_search(
                    pattern,
                    root,
                    target="content",
                    file_glob=file_glob,
                    limit=25,
                )
                state.candidates = _merge_candidates(
                    state.candidates, paths, tokens, exts, "content"
                )
                if top_confidence() >= CONFIDENCE_STOP:
                    break
                if state.internal_searches >= MAX_INTERNAL_SEARCHES:
                    break

    if top_confidence() >= CONFIDENCE_STOP:
        state.stopped_reason = "confidence_threshold"
    elif state.internal_searches >= MAX_INTERNAL_SEARCHES:
        state.stopped_reason = "internal_search_budget"
    elif state.candidates:
        state.stopped_reason = "stages_exhausted"
    else:
        state.stopped_reason = "not_found"

    return _result(query, state, max_candidates)


def _result(query: str, state: LocateState, max_candidates: int) -> Dict[str, Any]:
    cands = state.candidates[:max_candidates]
    return {
        "success": True,
        "query": query,
        "stages_run": list(state.stages_run),
        "stopped_reason": state.stopped_reason,
        "internal_searches": state.internal_searches,
        "already_completed": False,
        "candidates": [
            {
                "path": c.path,
                "confidence": round(c.confidence, 3),
                "stage": c.stage,
                "reason": c.reason,
            }
            for c in cands
        ],
    }


def locate_file_tool(
    query: str,
    roots: Optional[Sequence[str]] = None,
    extensions: Optional[Sequence[str]] = None,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    task_id: str = "default",
) -> str:
    """JSON string wrapper — runs LocateFileCapability, not a raw search loop."""
    from agent.capabilities.locate_file import LocateFileCapability

    cap = LocateFileCapability()
    result = cap.execute_objective(
        query,
        task_id=task_id,
        roots=roots,
        extensions=extensions,
        max_candidates=max_candidates,
    )
    payload = cap.to_tool_payload(result)
    return json.dumps(payload, ensure_ascii=False, indent=2)
