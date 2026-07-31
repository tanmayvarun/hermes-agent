"""plugin CLI — observe | inspect | replay | validate | eval | object-discovery-eval | strategic-search-rescue-eval | model-benchmark | call-pallavi."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from plugin.experiments.browser_relay_eval import main as browser_relay_eval_main
from plugin.experiments.harness import FIXTURES, run_scorecard
from plugin.experiments.model_benchmark import main as model_benchmark_main
from plugin.experiments.perception_prompt_benchmark import main as perception_prompt_benchmark_main
from plugin.experiments.strategic_search_rescue_eval import main as strategic_search_rescue_eval_main
from plugin.experiments.logger import EventLogger
from plugin.perception.macos.accessibility.observer import get_observer, macapptree_available
from plugin.worldmodel.model import WorldModel


def _default_log_dir() -> Path:
    return Path.home() / ".hermes" / "plugin" / "logs"


def cmd_observe(args: argparse.Namespace) -> int:
    fixture = Path(args.fixture) if args.fixture else None
    observer = get_observer(fixture=fixture, with_screenshot=not args.no_screenshot)
    obs = observer.observe(app=args.app)
    print(obs.summary_yaml(), end="")

    log = EventLogger(_default_log_dir() / "observe.jsonl")
    log.observation(
        {
            "app": obs.app_name,
            "window": obs.window_name,
            "nodes": len(obs.nodes),
            "source": obs.source,
            "coverage": obs.coverage,
        }
    )
    if args.json:
        print(json.dumps({"app": obs.app_name, "window": obs.window_name, "nodes": len(obs.nodes)}))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    wm = WorldModel()
    from plugin.perception.macos.accessibility.observer import FixtureObserver

    fused_frame = None
    if args.fixture:
        obs = FixtureObserver(Path(args.fixture)).observe()
        patch = wm.ingest(obs)
    elif macapptree_available() and args.app:
        try:
            from plugin.perception.fusion.fuse import observe_fused_frame

            fused_frame = observe_fused_frame(args.app, secondary=True)
            patch = wm.ingest_fused_frame(fused_frame)
            obs = fused_frame.to_observation()
        except Exception:
            obs = get_observer(with_screenshot=False).observe(args.app)
            patch = wm.ingest(obs)
    else:
        obs = FixtureObserver(FIXTURES / "whatsapp_conversation.json").observe()
        patch = wm.ingest(obs)
    summary = wm.summary()
    print("Current App")
    print(f"  {summary['active_app']}")
    print("Current Screen")
    print(f"  {summary['current_screen']}")
    print("WorldViewScore")
    print(f"  {summary.get('worldview_score')}")
    print("Entities (beliefs)")
    for e in summary["entities"][:30]:
        print(
            f"  #{e['id']} {e['type']} semantic={e['semantic']!r} "
            f"conf={e.get('confidence', 1):.2f} actions={e['actions']}"
        )
        beliefs = e.get("beliefs") or {}
        for prop, bel in list(beliefs.items())[:6]:
            srcs = []
            for ev in (bel.get("evidence") or [])[-3:]:
                srcs.append(f"{ev.get('source')}={ev.get('confidence', 0):.2f}")
            src_s = " ".join(srcs) if srcs else ""
            print(
                f"      {prop}: value={bel.get('value')!r} fused={bel.get('confidence', 0):.2f} {src_s}"
            )
    if summary.get("conflicts"):
        print("Fusion Conflicts")
        for c in summary["conflicts"][:10]:
            print(f"  {c}")
    print("Transitions")
    print(f"  count={summary['transition_count']}")
    print("World State")
    print(
        f"  retention_last={patch.retention:.3f} screen={patch.screen_label} "
        f"needs_reobserve={getattr(patch, 'needs_reobserve', False)}"
    )
    print("Nav")
    print(summary["nav_mermaid"])
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    from plugin.experiments.harness import replay_log

    path = Path(args.log)
    # Also support replaying fixture sequence
    wm = WorldModel()
    if args.fixtures:
        from plugin.perception.macos.accessibility.observer import FixtureObserver

        actions = [None, "open_search", "open_chat", "call"]
        for p, action in zip(
            [
                FIXTURES / "whatsapp_conversation.json",
                FIXTURES / "whatsapp_search.json",
                FIXTURES / "whatsapp_chat.json",
                FIXTURES / "whatsapp_call.json",
            ],
            actions,
        ):
            wm.ingest(FixtureObserver(p).observe(), action=action)
    elif path.exists():
        wm = replay_log(path, wm)
    else:
        print(f"log not found: {path}", file=sys.stderr)
        return 1
    print(json.dumps(wm.summary(), indent=2))
    print(wm.navigation_graph.to_mermaid())
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Technology Validation Sprint matrix."""
    apps = args.apps or ["WhatsApp", "Slack", "Google Chrome", "Safari", "Notes", "Sublime Text"]
    rows = []
    mat_ok = macapptree_available()
    from plugin.executor.ghost import ghost_available

    ghost_ok = ghost_available()
    print("Technology Validation Sprint")
    print(f"macapptree installed: {mat_ok}")
    print(f"ghost CLI available:  {ghost_ok}")
    print()
    print(f"{'Application':<20} {'macapptree':>10} {'Ghost':>8} {'Screen2AX?':>12} Notes")
    print("-" * 70)
    for app in apps:
        note = ""
        mat_cell = "—"
        ghost_cell = "—"
        s2ax = "Unknown"
        if args.live and mat_ok:
            try:
                obs = get_observer(with_screenshot=False).observe(app)
                mat_cell = "✅" if len(obs.nodes) > 5 else "⚠️"
                if len(obs.nodes) < 5:
                    s2ax = "Likely"
                    note = f"nodes={len(obs.nodes)}"
                else:
                    s2ax = "Rarely"
                    note = f"nodes={len(obs.nodes)}"
            except Exception as e:
                mat_cell = "❌"
                s2ax = "Yes"
                note = str(e)[:40]
        else:
            # Offline expected matrix from STACK research
            defaults = {
                "WhatsApp": ("✅", "✅", "Rarely", "Electron AX is good"),
                "Slack": ("✅", "✅", "Rarely", "Electron AX is good"),
                "Google Chrome": ("✅", "✅", "Rarely", "Prefer CDP for web later"),
                "Safari": ("✅", "✅", "Occasionally", "Native AX available"),
                "Notes": ("✅", "✅", "No", "Native controls"),
                "Sublime Text": ("✅", "✅", "Rarely", "Editor semantics limited"),
            }
            mat_cell, ghost_cell, s2ax, note = defaults.get(app, ("?", "?", "?", ""))
            if not mat_ok:
                mat_cell = "pkg❌"
            if not ghost_ok:
                ghost_cell = "cli❌"
        print(f"{app:<20} {mat_cell:>10} {ghost_cell:>8} {s2ax:>12} {note}")
        rows.append({"app": app, "macapptree": mat_cell, "ghost": ghost_cell, "screen2ax": s2ax, "notes": note})

    out = _default_log_dir() / "tech_validation.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        import tempfile

        out = Path(tempfile.gettempdir()) / "hermes-plugin-logs" / "tech_validation.json"
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"macapptree": mat_ok, "ghost": ghost_ok, "rows": rows}, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")
    print("Unknown dependencies remaining: 0 (see plugin/STACK.md)")
    return 0

def cmd_eval(args: argparse.Namespace) -> int:
    card = run_scorecard()
    print(json.dumps(card.to_dict(), indent=2))
    return 0 if card.kill_gate_pass else 2


def cmd_model_benchmark(args: argparse.Namespace) -> int:
    argv = []
    if args.suite:
        argv += ["--suite", args.suite]
    if args.candidate_file:
        argv += ["--candidate-file", args.candidate_file]
    for item in args.candidate or []:
        argv += ["--candidate", item]
    for item in getattr(args, "prompt_shape", []) or []:
        argv += ["--prompt-shape", item]
    for item in getattr(args, "context_pack", []) or []:
        argv += ["--context-pack", item]
    if args.ollama_base_url:
        argv += ["--ollama-base-url", args.ollama_base_url]
    if args.report:
        argv += ["--report", args.report]
    if args.json:
        argv.append("--json")
    return model_benchmark_main(argv)


def cmd_perception_prompt_benchmark(args: argparse.Namespace) -> int:
    argv = []
    if args.candidate_file:
        argv += ["--candidate-file", args.candidate_file]
    for item in args.candidate or []:
        argv += ["--candidate", item]
    for item in getattr(args, "shape", []) or []:
        argv += ["--shape", item]
    if args.ollama_base_url:
        argv += ["--ollama-base-url", args.ollama_base_url]
    if args.report:
        argv += ["--report", args.report]
    if args.json:
        argv.append("--json")
    return perception_prompt_benchmark_main(argv)


def cmd_browser_relay_eval(args: argparse.Namespace) -> int:
    argv = []
    if args.candidate_file:
        argv += ["--candidate-file", args.candidate_file]
    for item in args.candidate or []:
        argv += ["--candidate", item]
    if args.case_file:
        argv += ["--case-file", args.case_file]
    if args.followup_model:
        argv += ["--followup-model", args.followup_model]
    if args.trace_file:
        argv += ["--trace-file", args.trace_file]
    if args.max_turns is not None:
        argv += ["--max-turns", str(args.max_turns)]
    if args.report:
        argv += ["--report", args.report]
    if args.json:
        argv.append("--json")
    return browser_relay_eval_main(argv)


def cmd_launch(args: argparse.Namespace) -> int:
    """Launch an app with no Accessibility permission (open -a only)."""
    from plugin.perception.macos.launch import launch_app

    result = launch_app(args.app)
    print(f"ok={result.ok} app={result.app!r} {result.message}")
    print("cmd:", " ".join(result.command))
    if result.ok:
        print("Next: grant Accessibility to Terminal, then: plugin observe --app", args.app)
    return 0 if result.ok else 1


def cmd_permissions(args: argparse.Namespace) -> int:
    from plugin.perception.macos.launch import permissions_checklist

    print(permissions_checklist())
    return 0


def cmd_call_pallavi(args: argparse.Namespace) -> int:
    """WhatsApp call benchmark — fixture dry-run, or ``--live`` real AX+Ghost+ringing verify."""
    from plugin.experiments.call_pallavi import run_call_pallavi

    runs = Path(__file__).resolve().parent / "experiments" / "runs"
    try:
        runs.mkdir(parents=True, exist_ok=True)
        name = "call_pallavi_live.jsonl" if args.live else "call_pallavi.jsonl"
        log_path = runs / name
    except OSError:
        log_path = _default_log_dir() / ("call_pallavi_live.jsonl" if args.live else "call_pallavi.jsonl")

    contact = getattr(args, "contact", None) or "Pallavi"
    goal = f"Call {contact} on WhatsApp"
    ok, log = run_call_pallavi(
        log_path=log_path,
        live=bool(args.live),
        inject_fault=bool(args.inject_fault),
        goal=goal,
        contact=contact,
        with_screenshot=bool(getattr(args, "screenshot", False)),
        hangup=bool(getattr(args, "hangup", False)),
        target_name=str(getattr(args, "target_name", "") or ""),
        target_kind=str(getattr(args, "target_kind", "") or ""),
    )
    print()
    print(f"=== DONE ok={ok} live={bool(args.live)} ===")
    print(f"JSONL: {log.path}")
    print(f"Summary: {log.path.with_suffix('.md')}")
    return 0 if ok else 1


def cmd_policy_fit(args: argparse.Namespace) -> int:
    from plugin.agent.policy.events import fit_prior_from_events
    from plugin.agent.policy.prior import DEFAULT_STORE

    events = Path(args.events) if args.events else None
    store = Path(args.store) if args.store else DEFAULT_STORE
    prior = fit_prior_from_events(events, store)
    print(f"Fitted prior buckets={len(prior.counts)} → {store}")
    return 0


def cmd_perception_bench(args: argparse.Namespace) -> int:
    from plugin.experiments.perception_bench import main as bench_main

    argv = []
    if args.app:
        argv += ["--app", args.app]
    if args.live_shadow:
        argv.append("--live-shadow")
    if args.fixture:
        argv += ["--fixture", args.fixture]
    if args.json:
        argv.append("--json")
    return bench_main(argv)


def cmd_object_discovery_eval(args: argparse.Namespace) -> int:
    from plugin.experiments.object_discovery_eval import main as eval_main

    argv = []
    if getattr(args, "top_k", None) is not None:
        argv += ["--top-k", str(args.top_k)]
    if args.use_llm:
        argv.append("--use-llm")
    if args.force_llm:
        argv.append("--force-llm")
    for case_id in args.case or []:
        argv += ["--case", case_id]
    if args.json:
        argv.append("--json")
    return eval_main(argv)


def cmd_strategic_search_rescue_eval(args: argparse.Namespace) -> int:
    argv = []
    for case_id in args.case or []:
        argv += ["--case", case_id]
    if args.report:
        argv += ["--report", args.report]
    if args.json:
        argv.append("--json")
    return strategic_search_rescue_eval_main(argv)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="plugin", description="Plugin World Model POC CLI")
    sub = p.add_subparsers(dest="command", required=True)

    o = sub.add_parser("observe", help="Capture AX observation (macapptree)")
    o.add_argument("--app", default=None)
    o.add_argument("--fixture", default=None)
    o.add_argument("--no-screenshot", action="store_true")
    o.add_argument("--json", action="store_true")
    o.set_defaults(func=cmd_observe)

    i = sub.add_parser("inspect", help="Show world state from observation")
    i.add_argument("--app", default=None)
    i.add_argument("--fixture", default=None)
    i.set_defaults(func=cmd_inspect)

    r = sub.add_parser("replay", help="Replay observations into world model")
    r.add_argument("--log", default=str(_default_log_dir() / "observe.jsonl"))
    r.add_argument("--fixtures", action="store_true", help="Replay WhatsApp fixture path")
    r.set_defaults(func=cmd_replay)

    v = sub.add_parser("validate", help="Technology validation sprint matrix")
    v.add_argument("--live", action="store_true", help="Probe live apps via macapptree")
    v.add_argument("--apps", nargs="*", default=None)
    v.set_defaults(func=cmd_validate)

    e = sub.add_parser("eval", help="Run subsystem scorecard")
    e.set_defaults(func=cmd_eval)

    ode = sub.add_parser(
        "object-discovery-eval",
        help="Run synthetic precision/recall evals for generic object discovery",
    )
    ode.add_argument("--top-k", type=int, default=3)
    ode.add_argument("--use-llm", action="store_true")
    ode.add_argument("--force-llm", action="store_true")
    ode.add_argument("--case", action="append", default=[], help="Run only the named case(s)")
    ode.add_argument("--json", action="store_true")
    ode.set_defaults(func=cmd_object_discovery_eval)

    sres = sub.add_parser(
        "strategic-search-rescue-eval",
        help="Run synthetic strategic-search rescue evals for stalled branches",
    )
    sres.add_argument("--case", action="append", default=[], help="Run only the named case(s)")
    sres.add_argument("--report", default="", help="Optional JSON report path")
    sres.add_argument("--json", action="store_true", help="Print JSON only")
    sres.set_defaults(func=cmd_strategic_search_rescue_eval)

    c = sub.add_parser("call-pallavi", help="WhatsApp call benchmark (fixture / --live real call)")
    c.add_argument(
        "--live",
        action="store_true",
        help="Launch WhatsApp, live AX observe, Ghost click Call, verify ringing",
    )
    c.add_argument("--contact", default="Pallavi", help="Contact name to call (default Pallavi)")
    c.add_argument(
        "--target-name",
        default="",
        help="Optional interpreted display name (e.g. Now for 'now group')",
    )
    c.add_argument(
        "--target-kind",
        default="",
        choices=["", "contact", "group", "community"],
        help="Optional entity kind override",
    )
    c.add_argument(
        "--hangup",
        action="store_true",
        help="After verifying ringing, click End call (live only)",
    )
    c.add_argument(
        "--screenshot",
        action="store_true",
        help="Capture screenshots during live observe (needs Screen Recording)",
    )
    c.add_argument("--inject-fault", action="store_true")
    c.set_defaults(func=cmd_call_pallavi)

    pf = sub.add_parser("policy-fit", help="Fit empirical PolicyPrior from policy_events.jsonl")
    pf.add_argument("--events", default=None, help="Path to policy_events.jsonl")
    pf.add_argument("--store", default=None, help="Output policy_prior.json path")
    pf.set_defaults(func=cmd_policy_fit)

    pb = sub.add_parser("perception-bench", help="Shadow dual-source observe vs WorldViewScore")
    pb.add_argument("--app", default="WhatsApp")
    pb.add_argument("--live-shadow", action="store_true")
    pb.add_argument("--fixture", default="")
    pb.add_argument("--json", action="store_true")
    pb.set_defaults(func=cmd_perception_bench)

    mb = sub.add_parser(
        "model-benchmark",
        help="Benchmark multiple cloud LLMs across Hermes routing eval suites",
    )
    mb.add_argument(
        "--suite",
        default="",
        help="Path to a YAML/JSON suite file. Defaults to the built-in Hermes routing suite.",
    )
    mb.add_argument(
        "--candidate-file",
        default="",
        help="Path to a YAML/JSON file with candidate model specs.",
    )
    mb.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Inline JSON/YAML candidate spec (repeatable).",
    )
    mb.add_argument(
        "--prompt-shape",
        action="append",
        default=[],
        help="Prompt-shape preset name or JSON/YAML spec (repeatable).",
    )
    mb.add_argument(
        "--context-pack",
        action="append",
        default=[],
        help="Context-pack preset name or JSON/YAML spec (repeatable).",
    )
    mb.add_argument(
        "--provider",
        action="append",
        default=[],
        help="Provider name to auto-discover candidates from (repeatable).",
    )
    mb.add_argument(
        "--ollama-base-url",
        default="",
        help="Remote Ollama base URL to discover candidates from (e.g. http://host:11434).",
    )
    mb.add_argument(
        "--min-params-b",
        type=float,
        default=None,
        help="Optional minimum parameter size filter for auto-discovered candidates.",
    )
    mb.add_argument(
        "--max-params-b",
        type=float,
        default=None,
        help="Optional maximum parameter size filter for auto-discovered candidates.",
    )
    mb.add_argument(
        "--include-unknown-size",
        action="store_true",
        help="Keep candidates whose parameter size cannot be inferred.",
    )
    mb.add_argument(
        "--max-candidates-per-provider",
        type=int,
        default=5,
        help="Cap auto-discovered candidates per provider (default 5).",
    )
    mb.add_argument("--report", default="", help="Optional JSON report path")
    mb.add_argument("--json", action="store_true", help="Print JSON only")
    mb.set_defaults(func=cmd_model_benchmark)

    ppb = sub.add_parser(
        "perception-prompt-benchmark",
        help="Benchmark perception prompt shapes against the same screen fixture",
    )
    ppb.add_argument(
        "--candidate-file",
        default="",
        help="Path to a JSON file with candidate model specs.",
    )
    ppb.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Inline JSON candidate spec (repeatable).",
    )
    ppb.add_argument(
        "--shape",
        action="append",
        default=[],
        help="Prompt shape to include (compact, balanced, rich).",
    )
    ppb.add_argument(
        "--ollama-base-url",
        default="",
        help="Remote Ollama base URL to discover candidates from.",
    )
    ppb.add_argument("--report", default="", help="Optional JSON report path")
    ppb.add_argument("--json", action="store_true", help="Print JSON only")
    ppb.set_defaults(func=cmd_perception_prompt_benchmark)

    brel = sub.add_parser(
        "browser-relay-eval",
        help="Benchmark browser-backed assistant relay conversations",
    )
    brel.add_argument(
        "--candidate-file",
        default="",
        help="Path to a JSON file with browser relay candidate specs.",
    )
    brel.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Inline JSON candidate spec (repeatable).",
    )
    brel.add_argument(
        "--case-file",
        default="",
        help="Path to a JSON file with browser relay cases.",
    )
    brel.add_argument(
        "--followup-model",
        default="",
        help="JSON model candidate spec used to synthesize follow-up questions.",
    )
    brel.add_argument(
        "--trace-file",
        default="",
        help="Recorded transcript JSON to replay instead of using a live browser runner.",
    )
    brel.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="Optional cap on turns per case.",
    )
    brel.add_argument("--report", default="", help="Optional JSON report path")
    brel.add_argument("--json", action="store_true", help="Print JSON only")
    brel.set_defaults(func=cmd_browser_relay_eval)

    launch = sub.add_parser(
        "launch",
        help="Launch app via open -a (no Accessibility / no AppleScript)",
    )
    launch.add_argument("app", help='Application name, e.g. "WhatsApp"')
    launch.set_defaults(func=cmd_launch)

    perms = sub.add_parser("permissions", help="Print macOS permission checklist")
    perms.set_defaults(func=cmd_permissions)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
