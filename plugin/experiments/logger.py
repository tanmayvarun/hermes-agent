"""Append-only JSONL + console experiment logger.

Every step emits: Observation → WorldPatch → PlannerDecision → Execution → Result
with intermediate ok/fail status for offline analysis.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO


class EventLogger:
    def __init__(
        self,
        path: Path,
        *,
        also_console: bool = True,
        console: Optional[TextIO] = None,
        run_id: Optional[str] = None,
    ) -> None:
        self.path = Path(path)
        self.also_console = also_console
        self.console = console or sys.stdout
        self.run_id = run_id or f"run-{int(time.time())}"
        self._seq = 0
        self._steps_ok = 0
        self._steps_fail = 0
        # The stall watchdog writes from its own thread while the control loop
        # is blocked inside a call, so sequence numbers and appends are guarded.
        self._write_lock = threading.Lock()
        self._run_started_at_wall = time.time()
        self._run_started_at_monotonic = time.monotonic()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            import tempfile

            self.path = Path(tempfile.gettempdir()) / "hermes-plugin-logs" / self.path.name
            self.path.parent.mkdir(parents=True, exist_ok=True)
        # Truncate for a clean run file when starting a named benchmark
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def _reset_run_clock(self) -> None:
        self._run_started_at_wall = time.time()
        self._run_started_at_monotonic = time.monotonic()

    def _run_elapsed_s(self) -> float:
        try:
            return max(0.0, float(time.monotonic() - self._run_started_at_monotonic))
        except Exception:
            return 0.0

    def _run_elapsed_ms(self) -> int:
        return int(round(self._run_elapsed_s() * 1000.0))

    def begin_run(self, goal: str, meta: Optional[Dict[str, Any]] = None) -> None:
        self._reset_run_clock()
        self.log(
            "run_start",
            {
                "goal": goal,
                "run_id": self.run_id,
                "log_path": str(self.path),
                "run_elapsed_s": 0.0,
                "run_elapsed_ms": 0,
                "run_started_at": self._run_started_at_wall,
                **(meta or {}),
            },
            status="ok",
        )

    def log(
        self,
        kind: str,
        payload: Dict[str, Any],
        *,
        status: str = "ok",
        step: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self._write_lock:
            self._seq += 1
            if status == "ok":
                self._steps_ok += 1
            elif status in {"fail", "error"}:
                self._steps_fail += 1
            try:
                elapsed_s = float(payload["run_elapsed_s"]) if "run_elapsed_s" in payload else self._run_elapsed_s()
            except (TypeError, ValueError):
                elapsed_s = self._run_elapsed_s()
            rec: Dict[str, Any] = {
                "ts": time.time(),
                "run_elapsed_s": round(elapsed_s, 6),
                "run_elapsed_ms": int(round(elapsed_s * 1000.0)),
                "seq": self._seq,
                "run_id": self.run_id,
                "kind": kind,
                "status": status,
                **payload,
            }
            if step is not None:
                rec["step"] = step
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            if self.also_console:
                self._print(rec)
        return rec

    def _print(self, rec: Dict[str, Any]) -> None:
        kind = rec.get("kind", "?")
        status = rec.get("status", "?")
        seq = rec.get("seq", 0)
        step = rec.get("step")
        elapsed_s = rec.get("run_elapsed_s")
        mark = {"ok": "OK", "fail": "FAIL", "error": "ERR", "warn": "WARN"}.get(status, status.upper())
        prefix = f"[{seq:03d}][{mark}]"
        if step is not None:
            prefix += f"[step {step}]"
        if isinstance(elapsed_s, (int, float)):
            prefix += f"[+{float(elapsed_s):.2f}s]"
        # Compact one-line summary; details stay in JSONL
        detail_keys = (
            "message",
            "detail",
            "screen",
            "action",
            "semantic",
            "fixture",
            "backend",
            "goal",
            "retention",
            "nodes",
            "found",
            "expected",
            "rationale",
        )
        bits = [f"{k}={rec[k]!r}" for k in detail_keys if k in rec and rec[k] is not None]
        line = f"{prefix} {kind}"
        if bits:
            line += " | " + " ".join(bits[:8])
        if kind == "perception_summary":
            summary_text = str(rec.get("message") or rec.get("detail") or rec.get("text") or "").strip()
            width = max(72, len(summary_text) + 8 if summary_text else 72)
            header = "=" * width
            footer = "-" * width
            print(header, file=self.console)
            print("==== PERCEPTION SUMMARY ====", file=self.console)
            print(line, file=self.console)
            if summary_text:
                print(summary_text, file=self.console)
            print(footer, file=self.console)
            return
        print(line, file=self.console)

    def step(
        self,
        name: str,
        *,
        status: str = "ok",
        step: Optional[int] = None,
        **payload: Any,
    ) -> Dict[str, Any]:
        return self.log("step", {"name": name, **payload}, status=status, step=step)

    def observation(self, summary: Dict[str, Any], *, status: str = "ok", step: Optional[int] = None) -> None:
        self.log("observation", summary, status=status, step=step)

    def world_patch(self, patch: Dict[str, Any], *, status: str = "ok", step: Optional[int] = None) -> None:
        self.log("world_patch", patch, status=status, step=step)

    def planner_decision(self, decision: Dict[str, Any], *, status: str = "ok", step: Optional[int] = None) -> None:
        self.log("planner_decision", decision, status=status, step=step)

    def execution(self, result: Dict[str, Any], *, status: Optional[str] = None, step: Optional[int] = None) -> None:
        st = status or ("ok" if result.get("ok", True) else "fail")
        self.log("execution", result, status=st, step=step)

    def check(
        self,
        name: str,
        *,
        ok: bool,
        expected: Any = None,
        actual: Any = None,
        step: Optional[int] = None,
        **extra: Any,
    ) -> bool:
        self.log(
            "check",
            {
                "name": name,
                "expected": expected,
                "actual": actual,
                "message": "pass" if ok else "fail",
                **extra,
            },
            status="ok" if ok else "fail",
            step=step,
        )
        return ok

    def result(self, ok: bool, detail: str = "") -> None:
        self.log(
            "run_end",
            {
                "ok": ok,
                "detail": detail,
                "steps_ok": self._steps_ok,
                "steps_fail": self._steps_fail,
                "events": self._seq + 1,
                "log_path": str(self.path),
            },
            status="ok" if ok else "fail",
        )

    def read_all(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out

    def write_summary_md(self, path: Optional[Path] = None) -> Path:
        """Human-readable summary next to the JSONL."""
        out = path or self.path.with_suffix(".md")
        events = self.read_all()
        elapsed_values = [float(e.get("run_elapsed_s") or 0.0) for e in events if isinstance(e.get("run_elapsed_s"), (int, float))]
        final_elapsed = max(elapsed_values) if elapsed_values else 0.0
        lines = [
            f"# Run log — `{self.run_id}`",
            "",
            f"- JSONL: `{self.path}`",
            f"- Events: {len(events)}",
            f"- Final elapsed: `{final_elapsed:.2f}s`",
            "",
            "| seq | status | kind | detail |",
            "|----:|:------:|------|--------|",
        ]
        for e in events:
            detail = e.get("message") or e.get("detail") or e.get("name") or e.get("screen") or e.get("goal") or ""
            if e.get("kind") == "planner_decision" and e.get("steps"):
                detail = f"{e.get('goal')}: " + " → ".join(
                    f"{s.get('action')}({s.get('semantic_target') or s.get('text') or ''})"
                    for s in e["steps"]
                )
            detail = str(detail).replace("|", "\\|")[:120]
            lines.append(f"| {e.get('seq')} | {e.get('status')} | {e.get('kind')} | {detail} |")
        fails = [e for e in events if e.get("status") in {"fail", "error"}]
        lines += ["", "## Failures", ""]
        if not fails:
            lines.append("_None._")
        else:
            for e in fails:
                lines.append(f"- seq={e.get('seq')} `{e.get('kind')}`: {json.dumps(e, default=str)[:200]}")
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out
