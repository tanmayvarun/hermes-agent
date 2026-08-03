"""Component-correctness eval for the self-contained entity-resolution skill.

Entity resolution is a *semantic* task — "which candidate is the one the goal
means?" — not a bag of WhatsApp string rules. The skill (`resolve()`) is
designed to be robust on its own: it tries a deterministic fast path, judges its
*own* confidence, and consults an LLM over the candidates whenever it is not sure
enough. The executive brain is the outer evaluator of the skill's response, not
the arbiter of that internal fast-path/escalate decision.

This eval drives the real skill end-to-end across *different apps* — WhatsApp
contacts, YouTube videos/channels, Google search results, filesystem paths, and
Slack channels/DMs — with a stubbed LLM standing in for the escalation path. No
domain-specific expectation appears anywhere: if the same skill fast-paths a
unique file open and escalates an ambiguous "which general channel" post exactly
as it does for chats, the logic transfers; if a case flips, the skill has quietly
re-specialised around one app.

The dangerous metric is asymmetric:

- false_fast_path_rate : of cases that SHOULD escalate (ambiguous / risky), how
                         many did the skill wave through on the deterministic
                         fast path without consulting the LLM? Under an
                         irreversible action this is how you send to a stranger.
                         Must stay at zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from plugin.agent.capabilities.resolve_entity import (
    ResolutionRequest,
    resolve_many,
    resolve_one,
)


@dataclass(frozen=True)
class ResolutionCase:
    """One resolution situation with the decision a correct skill reaches.

    ``expect_fast_path`` means the deterministic pick is a confident true
    positive the skill acts on without an LLM. Its complement means the evidence
    is not good enough, so the skill must consult the LLM (or, under an
    irreversible action left ambiguous, abstain to the user).
    """

    id: str
    domain: str
    referent: str
    candidates: Sequence[Any]
    consequence: str
    expect_fast_path: bool


# Labelled corpus. One skill, five real apps, no per-domain rule. Each case is a
# situation a user could actually hand the agent ("open Pallavi", "forward this
# to Aakash", "play the python tutorial", "post in general"), paired with the
# decision a correct resolver reaches — fast-path a confident true positive, or
# escalate/abstain when the evidence is genuinely ambiguous or the action is
# irreversible.
RESOLUTION_CASES: Sequence[ResolutionCase] = (
    # ---- WhatsApp: forward/open a chat --------------------------------------
    ResolutionCase(
        "wa_open_unique_contact", "whatsapp", "Priya",
        ["Priya", "Rahul", "Mom"], "reversible", True,
    ),
    ResolutionCase(
        "wa_send_self_note", "whatsapp", "Tanmay",
        [{"label": "Tanmay (You)", "hints": ["self"]}, {"label": "Tanvi"}],
        "irreversible", True,
    ),
    ResolutionCase(
        # The ZarooratWala row: contact name carries a message preview + URL.
        "wa_open_search_row_with_preview", "whatsapp", "Pallavi",
        ["Pallavi - You: https://www.zarooratwala.com/item/42", "Pallavi Ather Gen3"],
        "reversible", True,
    ),
    ResolutionCase(
        # A person vs. group threads that merely contain the name.
        "wa_send_person_not_group", "whatsapp", "Aakash",
        ["Aakash", "Aakash <> Tanmay", "Aakash & Family"], "irreversible", True,
    ),
    ResolutionCase(
        # Two real namesakes as a send destination — cannot fast-path.
        "wa_send_two_namesakes", "whatsapp", "Rahul",
        ["Rahul Sharma", "Rahul Verma"], "irreversible", False,
    ),

    # ---- YouTube: open/play a video or channel ------------------------------
    ResolutionCase(
        "yt_open_exact_title", "youtube", "Me at the zoo",
        ["Me at the zoo", "Zoo Tour Vlog"], "reversible", True,
    ),
    ResolutionCase(
        # Exact channel name beats an impostor namesake ("Veritasium2").
        "yt_open_channel_vs_impostor", "youtube", "Veritasium",
        ["Veritasium", "Veritasium2", "Veritasium Clips"], "reversible", True,
    ),
    ResolutionCase(
        # A description, not a title: several tutorials match loosely.
        "yt_play_ambiguous_fragment", "youtube", "python tutorial",
        ["Python Tutorial for Beginners", "Advanced Python Tutorial", "Learn Python Full Course"],
        "reversible", False,
    ),

    # ---- Google Search: open a result ---------------------------------------
    ResolutionCase(
        "google_open_official_site", "google", "OpenAI",
        ["OpenAI", "OpenAI Blog", "OpenAI Platform"], "reversible", True,
    ),
    ResolutionCase(
        "google_open_exact_domain", "google", "python.org",
        ["python.org", "python.org/downloads", "realpython.com"], "reversible", True,
    ),
    ResolutionCase(
        # Classic ambiguous query — three unrelated senses of "jaguar".
        "google_ambiguous_query", "google", "jaguar",
        ["Jaguar (car)", "Jaguar (animal)", "Jacksonville Jaguars"], "reversible", False,
    ),

    # ---- Filesystem: open vs. delete ----------------------------------------
    ResolutionCase(
        "fs_open_unique_file", "filesystem", "budget_2026.xlsx",
        ["budget_2026.xlsx", "budget_2025.xlsx"], "reversible", True,
    ),
    ResolutionCase(
        "fs_open_base_name", "filesystem", "resume",
        ["resume", "resume-old", "resume-2024"], "reversible", True,
    ),
    ResolutionCase(
        # Exact filename is safe to delete without a second opinion.
        "fs_delete_exact_file", "filesystem", "old_logs.zip",
        ["old_logs.zip", "old_logs_backup.zip"], "irreversible", True,
    ),
    ResolutionCase(
        # "draft" matches three versions — never delete on a guess.
        "fs_delete_ambiguous_draft", "filesystem", "draft",
        ["draft_v1.docx", "draft_v2.docx", "draft_final.docx"], "irreversible", False,
    ),

    # ---- Slack: open a channel/DM vs. post ----------------------------------
    ResolutionCase(
        "slack_open_unique_channel", "slack", "#engineering",
        ["#engineering", "#eng-random", "#design"], "reversible", True,
    ),
    ResolutionCase(
        "slack_dm_self_marker", "slack", "Tanmay",
        [{"label": "Tanmay (you)", "hints": ["self"]}, {"label": "Tanya"}],
        "irreversible", True,
    ),
    ResolutionCase(
        "slack_post_exact_channel", "slack", "#incidents",
        ["#incidents", "#incident-reports"], "irreversible", True,
    ),
    ResolutionCase(
        # Which "general"? Posting is irreversible — escalate.
        "slack_post_ambiguous_general", "slack", "general",
        ["#general", "#general-announcements", "#general-random"], "irreversible", False,
    ),
)


class _StubResolver:
    """A competent LLM stand-in: records consultations and picks a candidate.

    It resolves ambiguity by returning the first candidate with high confidence,
    so escalation cases produce a concrete `llm` result. A real deployment swaps
    this for `LlmEntityResolver`; the eval only cares whether the skill *decided*
    to consult.
    """

    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
        self.calls += 1
        cands = [c.get("label") for c in packet.get("candidates") or [] if c.get("label")]
        if not cands:
            return {}
        return {"chosen": cands[0], "candidates": [{"label": cands[0], "score": 0.9, "why": "stub"}]}


@dataclass
class ResolutionScore:
    total: int = 0
    correct: int = 0
    fast_path_expected: int = 0
    fast_path_hits: int = 0
    escalate_expected: int = 0
    escalate_hits: int = 0
    false_fast_paths: int = 0
    domains: int = 0
    failures: List[str] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return round(self.correct / self.total, 4) if self.total else 1.0

    @property
    def fast_path_true_positive_rate(self) -> float:
        return round(self.fast_path_hits / self.fast_path_expected, 4) if self.fast_path_expected else 1.0

    @property
    def escalation_recall(self) -> float:
        return round(self.escalate_hits / self.escalate_expected, 4) if self.escalate_expected else 1.0

    @property
    def false_fast_path_rate(self) -> float:
        """The dangerous error: fast-pathed a case that should have escalated."""
        return round(self.false_fast_paths / self.escalate_expected, 4) if self.escalate_expected else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cases": self.total,
            "domains": self.domains,
            "accuracy": self.accuracy,
            "fast_path_true_positive_rate": self.fast_path_true_positive_rate,
            "escalation_recall": self.escalation_recall,
            "false_fast_path_rate": self.false_fast_path_rate,
            "failures": list(self.failures)[:8],
        }


def score_resolution_cases(cases: Sequence[ResolutionCase] = RESOLUTION_CASES) -> ResolutionScore:
    """Run every labelled case through the real skill and grade the decision."""
    score = ResolutionScore()
    seen_domains = set()
    for case in cases:
        stub = _StubResolver()
        result = resolve_one(
            ResolutionRequest(
                referent=case.referent,
                candidates=list(case.candidates),
                consequence=case.consequence,
            ),
            resolver=stub,
        )
        # Fast path == the skill acted on its own deterministic pick without
        # consulting the LLM.
        fast_path = result.method == "deterministic" and not result.escalated and stub.calls == 0

        score.total += 1
        seen_domains.add(case.domain)
        if fast_path == case.expect_fast_path:
            score.correct += 1
        else:
            score.failures.append(
                f"{case.id}[{case.domain}]: fast_path={fast_path} "
                f"(want {case.expect_fast_path}); method={result.method} "
                f"escalated={result.escalated} evidence={result.evidence}"
            )

        if case.expect_fast_path:
            score.fast_path_expected += 1
            if fast_path:
                score.fast_path_hits += 1
        else:
            score.escalate_expected += 1
            if not fast_path:
                score.escalate_hits += 1
            else:
                score.false_fast_paths += 1

    score.domains = len(seen_domains)
    return score


@dataclass(frozen=True)
class MultiCase:
    """A resolve-many situation: which candidates the skill should return."""

    id: str
    domain: str
    referent: str
    candidates: Sequence[Any]
    expected: frozenset


# Recall-oriented corpus: the skill must return the whole matching set (and
# nothing unrelated), across the same five apps. Predicate-style filters
# ("idle > 1yr", "size > 1GB") live upstream in search/query — these only test
# semantic-closeness recall over a given candidate set.
MULTI_CASES: Sequence[MultiCase] = (
    MultiCase(
        "wa_all_namesakes", "whatsapp", "Tanmay",
        ["Tanmay Kumar", "Tanmay Singh", "Aakash"],
        frozenset({"Tanmay Kumar", "Tanmay Singh"}),
    ),
    MultiCase(
        "yt_all_channel_variants", "youtube", "MrBeast",
        ["MrBeast", "MrBeast Gaming", "MrBeast Shorts", "PewDiePie"],
        frozenset({"MrBeast", "MrBeast Gaming", "MrBeast Shorts"}),
    ),
    MultiCase(
        "google_all_python_results", "google", "python",
        ["python.org", "docs.python.org", "realpython.com", "java.com"],
        frozenset({"python.org", "docs.python.org", "realpython.com"}),
    ),
    MultiCase(
        "fs_all_reports", "filesystem", "report",
        ["report_jan.pdf", "report_feb.pdf", "budget.xlsx"],
        frozenset({"report_jan.pdf", "report_feb.pdf"}),
    ),
    MultiCase(
        "slack_all_general_channels", "slack", "general",
        ["#general", "#general-announcements", "#random"],
        frozenset({"#general", "#general-announcements"}),
    ),
)


@dataclass
class MultiScore:
    total: int = 0
    exact_set_matches: int = 0
    precision_sum: float = 0.0
    recall_sum: float = 0.0
    domains: int = 0
    failures: List[str] = field(default_factory=list)

    @property
    def set_exact_match_rate(self) -> float:
        return round(self.exact_set_matches / self.total, 4) if self.total else 1.0

    @property
    def mean_precision(self) -> float:
        return round(self.precision_sum / self.total, 4) if self.total else 1.0

    @property
    def mean_recall(self) -> float:
        return round(self.recall_sum / self.total, 4) if self.total else 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cases": self.total,
            "domains": self.domains,
            "set_exact_match_rate": self.set_exact_match_rate,
            "mean_precision": self.mean_precision,
            "mean_recall": self.mean_recall,
            "failures": list(self.failures)[:8],
        }


def score_multi_resolution_cases(cases: Sequence[MultiCase] = MULTI_CASES) -> MultiScore:
    """Grade resolve_many recall/precision across domains on the labelled set."""
    score = MultiScore()
    seen_domains = set()
    for case in cases:
        got = set(
            resolve_many(case.referent, list(case.candidates)).matches
        )
        expected = set(case.expected)
        score.total += 1
        seen_domains.add(case.domain)
        tp = len(got & expected)
        precision = tp / len(got) if got else (1.0 if not expected else 0.0)
        recall = tp / len(expected) if expected else 1.0
        score.precision_sum += precision
        score.recall_sum += recall
        if got == expected:
            score.exact_set_matches += 1
        else:
            score.failures.append(f"{case.id}[{case.domain}]: got {sorted(got)} want {sorted(expected)}")
    score.domains = len(seen_domains)
    return score


def summarize_resolution(score: ResolutionScore | None = None) -> Dict[str, Any]:
    summary = (score or score_resolution_cases()).to_dict()
    summary["multi"] = score_multi_resolution_cases().to_dict()
    return summary
