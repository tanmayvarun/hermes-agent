"""ExecutiveWorkspace — the single authoritative record of the task right now.

Before this module, "what does the agent believe about the task" was answered by
whichever store you happened to read: the open conversation lived in six of
them, the phase in three, attempt history in four, and nothing reconciled them.

The workspace holds one copy of each and takes writes only through ``commit``,
which runs a critic over the proposal the way
``world_critic.critique_world_proposal`` does for the world document. A caller
never assigns to workspace state; it proposes, and the verdict says what was
accepted and why. That is what makes belief changes explainable — and, later,
measurable, since every rejection is recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from plugin.agent.executive.questions import (
    Hypothesis,
    InformationGap,
    OpenQuestion,
    QuestionLedger,
)

MAX_ATTEMPTS = 32
MAX_TRANSITIONS = 64
MAX_DECISIONS = 64
MAX_CONTRADICTIONS = 32

# Surfaces where an empty open-conversation reading is far more likely to be a
# perception miss than a real close. Mirrors world_critic's wipe protection.
CONVERSATION_DESCENDED = {"conversation", "context_menu", "forward_picker", "dialog"}

# Phase ladders are domain knowledge, not core knowledge: a domain registers the
# order its phases advance in, and the critic refuses unjustified regression.
# The core has no opinion about what the phases mean.
PHASE_LADDERS: Dict[str, Tuple[str, ...]] = {
    "whatsapp_forward_message": (
        "reach_source",
        "hunt_content",
        "act_on_content",
        "invoke_forward",
        "choose_destination",
        "committed",
        "verified",
    ),
    "whatsapp_voice_call": ("reach_source", "act_on_content", "committed", "verified"),
}


def phase_ladder_for(goal_kind: str) -> Tuple[str, ...]:
    return PHASE_LADDERS.get(str(goal_kind or "").strip().lower(), ())


def register_phase_ladder(goal_kind: str, ladder: Sequence[str]) -> None:
    """Let a domain declare its own phase order without editing the core."""
    key = str(goal_kind or "").strip().lower()
    if key:
        PHASE_LADDERS[key] = tuple(str(p).strip().lower() for p in ladder if str(p).strip())


# Success conditions and constraints are the *contract* of a task: what "done"
# means and what must hold along the way. Like the phase ladder, they are domain
# knowledge the core merely stores — the workspace, not a task-specific state
# object, is the authoritative record of the task contract. A domain registers
# its contract; the core has no opinion about the content.
GOAL_CONTRACTS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "whatsapp_forward_message": {
        "success_conditions": (
            "source conversation reached",
            "source content identified",
            "forward invoked on the content",
            "destination chosen",
            "message delivered to the destination",
        ),
        "constraints": (
            "send is irreversible: confirm the destination before committing",
            "forward the content from the correct source conversation",
        ),
    },
    "whatsapp_voice_call": {
        "success_conditions": (
            "target conversation reached",
            "voice call started",
            "call connected or ringing",
        ),
        "constraints": (
            "placing a call is irreversible: confirm the contact before calling",
        ),
    },
}


def goal_contract_for(goal_kind: str) -> Dict[str, Tuple[str, ...]]:
    return GOAL_CONTRACTS.get(str(goal_kind or "").strip().lower(), {})


def register_goal_contract(
    goal_kind: str,
    *,
    success_conditions: Sequence[str] = (),
    constraints: Sequence[str] = (),
) -> None:
    """Let a domain declare its success conditions and constraints in the core."""
    key = str(goal_kind or "").strip().lower()
    if key:
        GOAL_CONTRACTS[key] = {
            "success_conditions": tuple(str(s).strip() for s in success_conditions if str(s).strip()),
            "constraints": tuple(str(c).strip() for c in constraints if str(c).strip()),
        }


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


# ------------------------------------------------------------------- records


# The epistemic status a claim can carry. A belief is not just a value and a
# confidence: it matters whether the agent *saw* it, *inferred* it, is only
# *predicting* it, does not know it, or has seen it *contradicted*. Downstream
# reasoning (and the eval that scores unsupported confidence) reads this.
CLAIM_STATUSES = ("observed", "inferred", "predicted", "unknown", "contradicted")


@dataclass
class Claim:
    """A believed value, with who said it, on what evidence, and how known."""

    value: str = ""
    source: str = ""
    confidence: float = 0.0
    frame: int = 0
    evidence: str = ""
    status: str = "observed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "source": self.source,
            "confidence": round(float(self.confidence or 0.0), 3),
            "frame": int(self.frame),
            "evidence": self.evidence[:160],
            "status": self.status,
        }


@dataclass
class Contradiction:
    """A fact whose established value was challenged by a different reading.

    Kept as a first-class list (not just a flip counter) so the executive can
    see *what* disagreed, who said each side, and how the workspace resolved it.
    """

    key: str = ""
    prior: str = ""
    proposed: str = ""
    prior_source: str = ""
    proposed_source: str = ""
    frame: int = 0
    resolution: str = "unresolved"  # kept_prior | took_proposed | unresolved

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "prior": self.prior,
            "proposed": self.proposed,
            "prior_source": self.prior_source,
            "proposed_source": self.proposed_source,
            "frame": int(self.frame),
            "resolution": self.resolution,
        }


@dataclass
class AttemptRecord:
    """One thing the agent tried, and what came back."""

    frame: int = 0
    kind: str = "action"  # action | search | probe
    action: str = ""
    target: str = ""
    text: str = ""
    outcome: str = ""

    def identity(self) -> Tuple[str, str, str, str]:
        return (self.kind, self.action.lower(), self.target.lower(), self.text.lower())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame": int(self.frame),
            "kind": self.kind,
            "action": self.action,
            "target": self.target,
            "text": self.text,
            "outcome": self.outcome[:120],
        }

    def as_search_entry(self) -> Dict[str, Any]:
        """The shape the search-refinement code has always read."""
        return {"q": self.text or self.target, "outcome": self.outcome[:120]}


@dataclass
class TransitionRecord:
    frame: int = 0
    action: str = ""
    family: str = ""
    before_surface: str = ""
    after_surface: str = ""
    outcome: str = ""
    progress_delta: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame": int(self.frame),
            "action": self.action,
            "family": self.family,
            "before_surface": self.before_surface,
            "after_surface": self.after_surface,
            "outcome": self.outcome,
            "progress_delta": round(float(self.progress_delta or 0.0), 3),
        }


@dataclass
class GoalState:
    kind: str = ""
    objective: str = ""
    subject: str = ""  # source conversation / primary entity
    destination: str = ""
    query: str = ""
    success_conditions: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)

    @classmethod
    def from_goal(cls, goal: Any) -> "GoalState":
        if goal is None:
            return cls()
        kind = str(getattr(goal, "kind", "") or "")
        contract = goal_contract_for(kind)
        return cls(
            kind=kind,
            objective=str(getattr(goal, "description", "") or getattr(goal, "prompt", "") or ""),
            subject=str(getattr(goal, "contact", "") or ""),
            destination=str(getattr(goal, "target_contact", "") or ""),
            query=str(getattr(goal, "link_query", "") or ""),
            success_conditions=list(contract.get("success_conditions", ())),
            constraints=list(contract.get("constraints", ())),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "objective": self.objective,
            "subject": self.subject,
            "destination": self.destination,
            "query": self.query,
            "success_conditions": list(self.success_conditions),
            "constraints": list(self.constraints),
        }


@dataclass
class Intent:
    """What the executive is trying to do right now, and how it will know."""

    objective: str = ""
    completion_predicate: str = ""
    methods: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective": self.objective,
            "completion_predicate": self.completion_predicate,
            "methods": list(self.methods),
        }


@dataclass
class Budgets:
    max_steps: int = 0
    steps_used: int = 0
    model_calls: int = 0
    wall_clock_s: float = 0.0

    @property
    def steps_left(self) -> int:
        if self.max_steps <= 0:
            return 0
        return max(0, self.max_steps - self.steps_used)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_steps": self.max_steps,
            "steps_used": self.steps_used,
            "steps_left": self.steps_left,
            "model_calls": self.model_calls,
            "wall_clock_s": round(float(self.wall_clock_s or 0.0), 2),
        }


# ------------------------------------------------------------ propose/commit


@dataclass
class WorkspaceProposal:
    """A request to change the workspace. Never applied directly."""

    source: str = ""
    frame: int = 0
    confidence: float = 0.0
    evidence: str = ""
    surface: str = ""  # the surface the proposal was read on, for wipe protection
    open_conversation: Optional[str] = None
    phase: Optional[str] = None
    # Arbitrary believed facts this reading offers, keyed by name. Each value is
    # a Claim (value + confidence + evidence); the workspace arbitrates against
    # any established belief and records a contradiction when they disagree.
    facts: Dict[str, "Claim"] = field(default_factory=dict)
    allow_phase_regression: bool = False
    attempts: List[AttemptRecord] = field(default_factory=list)
    transitions: List[TransitionRecord] = field(default_factory=list)
    intent: Optional[Intent] = None
    budgets: Optional[Dict[str, Any]] = None
    # Questions the reading raises, candidate answers it proposes, gaps it must
    # close, and resolutions it can now record. Exploration keys off these.
    ask: List[OpenQuestion] = field(default_factory=list)
    hypotheses: List[Hypothesis] = field(default_factory=list)
    gaps: List[InformationGap] = field(default_factory=list)
    answers: List[Tuple[str, str, str]] = field(default_factory=list)  # (question, answer, evidence)
    abandon: List[Tuple[str, str]] = field(default_factory=list)  # (question, reason)


@dataclass
class CommitDecision:
    field: str
    verdict: str  # accept | reject | unchanged
    reason: str
    prior: Any = None
    proposed: Any = None
    accepted: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "verdict": self.verdict,
            "reason": self.reason,
            "prior": self.prior,
            "proposed": self.proposed,
            "accepted": self.accepted,
        }


@dataclass
class CommitVerdict:
    source: str = ""
    frame: int = 0
    decisions: List[CommitDecision] = field(default_factory=list)

    @property
    def accepted_fields(self) -> List[str]:
        return [d.field for d in self.decisions if d.verdict == "accept"]

    @property
    def rejected_fields(self) -> List[str]:
        return [d.field for d in self.decisions if d.verdict == "reject"]

    def accepted(self, name: str) -> bool:
        return any(d.field == name and d.verdict == "accept" for d in self.decisions)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "frame": self.frame,
            "accepted": self.accepted_fields,
            "rejected": self.rejected_fields,
            "decisions": [d.to_dict() for d in self.decisions],
        }


# --------------------------------------------------------------- the record


@dataclass
class ExecutiveWorkspace:
    """The task record. Read freely; write only through ``commit``."""

    goal: GoalState = field(default_factory=GoalState)
    intention: Intent = field(default_factory=Intent)
    budgets: Budgets = field(default_factory=Budgets)
    questions: QuestionLedger = field(default_factory=QuestionLedger)
    frame: int = 0

    _conversation: Claim = field(default_factory=Claim)
    _phase: Claim = field(default_factory=Claim)
    _facts: Dict[str, Claim] = field(default_factory=dict)
    _contradictions: List[Contradiction] = field(default_factory=list)
    _attempts: List[AttemptRecord] = field(default_factory=list)
    _transitions: List[TransitionRecord] = field(default_factory=list)
    _log: List[CommitVerdict] = field(default_factory=list)
    _phase_regressions: int = 0
    _belief_flips: int = 0

    # ------------------------------------------------------------- readers

    @property
    def open_conversation(self) -> str:
        return self._conversation.value

    @property
    def open_conversation_claim(self) -> Claim:
        return self._conversation

    @property
    def phase(self) -> str:
        return self._phase.value

    @property
    def phase_claim(self) -> Claim:
        return self._phase

    @property
    def attempts(self) -> List[AttemptRecord]:
        return list(self._attempts)

    @property
    def transitions(self) -> List[TransitionRecord]:
        return list(self._transitions)

    @property
    def commit_log(self) -> List[CommitVerdict]:
        return list(self._log)

    @property
    def facts(self) -> Dict[str, Claim]:
        return dict(self._facts)

    def fact(self, key: str) -> Optional[Claim]:
        return self._facts.get(_norm(key).lower())

    def fact_value(self, key: str, default: str = "") -> str:
        claim = self._facts.get(_norm(key).lower())
        return claim.value if claim is not None else default

    @property
    def contradictions(self) -> List[Contradiction]:
        return list(self._contradictions)

    @property
    def unresolved_contradictions(self) -> List[Contradiction]:
        return [c for c in self._contradictions if c.resolution == "unresolved"]

    @property
    def phase_regressions(self) -> int:
        return self._phase_regressions

    @property
    def belief_flips(self) -> int:
        """How often a settled belief was replaced by a different value."""
        return self._belief_flips

    def attempts_of(self, kind: str) -> List[AttemptRecord]:
        want = _norm(kind).lower()
        return [a for a in self._attempts if a.kind == want]

    def search_attempts(self) -> List[Dict[str, Any]]:
        return [a.as_search_entry() for a in self.attempts_of("search")]

    def ladder(self) -> Tuple[str, ...]:
        return phase_ladder_for(self.goal.kind)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal.to_dict(),
            "intention": self.intention.to_dict(),
            "budgets": self.budgets.to_dict(),
            "frame": self.frame,
            "open_conversation": self._conversation.to_dict(),
            "phase": self._phase.to_dict(),
            "facts": {k: v.to_dict() for k, v in self._facts.items()},
            "contradictions": [c.to_dict() for c in self._contradictions[-8:]],
            "attempts": [a.to_dict() for a in self._attempts[-8:]],
            "transitions": [t.to_dict() for t in self._transitions[-8:]],
            "questions": self.questions.to_dict(),
            "phase_regressions": self._phase_regressions,
            "belief_flips": self._belief_flips,
        }

    # -------------------------------------------------------------- writer

    def commit(self, proposal: WorkspaceProposal) -> CommitVerdict:
        """The only mutation path. Returns what was accepted and why."""
        verdict = CommitVerdict(source=proposal.source, frame=proposal.frame)
        if proposal.frame:
            self.frame = max(self.frame, int(proposal.frame))

        self._commit_conversation(proposal, verdict)
        self._commit_phase(proposal, verdict)
        self._commit_facts(proposal, verdict)
        self._commit_attempts(proposal, verdict)
        self._commit_transitions(proposal, verdict)
        self._commit_intent(proposal, verdict)
        self._commit_budgets(proposal, verdict)
        self._commit_questions(proposal, verdict)

        self._log.append(verdict)
        if len(self._log) > MAX_DECISIONS:
            self._log = self._log[-MAX_DECISIONS:]
        return verdict

    # ------------------------------------------------------------ internals

    def _commit_conversation(self, proposal: WorkspaceProposal, verdict: CommitVerdict) -> None:
        if proposal.open_conversation is None:
            return
        proposed = _norm(proposal.open_conversation)
        prior = self._conversation.value
        surface = _norm(proposal.surface).lower()

        # Search-field chrome is not a conversation referent. Refuse it the same
        # way the world critic does, so AX "Q Search|" cannot own the workspace.
        try:
            from plugin.agent.world_critic import is_search_field_echo
        except Exception:  # pragma: no cover
            is_search_field_echo = lambda _t: False  # type: ignore
        if proposed and is_search_field_echo(proposed):
            verdict.decisions.append(
                CommitDecision(
                    "open_conversation",
                    "reject",
                    "search-field chrome is not an open conversation",
                    prior,
                    proposed,
                    prior,
                )
            )
            return

        if proposed == prior:
            verdict.decisions.append(
                CommitDecision("open_conversation", "unchanged", "same value", prior, proposed, prior)
            )
            return
        if not proposed:
            if prior and surface in CONVERSATION_DESCENDED:
                verdict.decisions.append(
                    CommitDecision(
                        "open_conversation",
                        "reject",
                        f"refuse to wipe {prior!r} while on {surface!r}",
                        prior,
                        proposed,
                        prior,
                    )
                )
                return
            if prior and not surface:
                verdict.decisions.append(
                    CommitDecision(
                        "open_conversation",
                        "reject",
                        "empty reading with no surface context is not evidence of a close",
                        prior,
                        proposed,
                        prior,
                    )
                )
                return
        if prior and proposed:
            self._belief_flips += 1
        self._conversation = Claim(
            value=proposed,
            source=proposal.source,
            confidence=float(proposal.confidence or 0.0),
            frame=int(proposal.frame),
            evidence=_norm(proposal.evidence),
        )
        verdict.decisions.append(
            CommitDecision("open_conversation", "accept", proposal.source, prior, proposed, proposed)
        )

    def _commit_phase(self, proposal: WorkspaceProposal, verdict: CommitVerdict) -> None:
        if proposal.phase is None:
            return
        proposed = _norm(proposal.phase).lower()
        prior = self._phase.value
        if not proposed:
            verdict.decisions.append(
                CommitDecision("phase", "reject", "empty phase", prior, proposed, prior)
            )
            return
        if proposed == prior:
            verdict.decisions.append(
                CommitDecision("phase", "unchanged", "same phase", prior, proposed, prior)
            )
            return

        ladder = self.ladder()
        if prior and ladder and prior in ladder and proposed in ladder:
            if ladder.index(proposed) < ladder.index(prior):
                if not proposal.allow_phase_regression:
                    verdict.decisions.append(
                        CommitDecision(
                            "phase",
                            "reject",
                            f"unjustified regression {prior!r} -> {proposed!r}",
                            prior,
                            proposed,
                            prior,
                        )
                    )
                    return
                self._phase_regressions += 1

        self._phase = Claim(
            value=proposed,
            source=proposal.source,
            confidence=float(proposal.confidence or 0.0),
            frame=int(proposal.frame),
            evidence=_norm(proposal.evidence),
        )
        verdict.decisions.append(
            CommitDecision("phase", "accept", proposal.source, prior, proposed, proposed)
        )

    def _commit_facts(self, proposal: WorkspaceProposal, verdict: CommitVerdict) -> None:
        for raw_key, claim in (proposal.facts or {}).items():
            key = _norm(raw_key).lower()
            if not key:
                verdict.decisions.append(
                    CommitDecision("fact", "reject", "empty fact key", None, None, None)
                )
                continue
            proposed_value = _norm(getattr(claim, "value", ""))
            status = str(getattr(claim, "status", "") or "observed").strip().lower()
            if status not in CLAIM_STATUSES:
                status = "observed"
            incoming = Claim(
                value=proposed_value,
                source=getattr(claim, "source", "") or proposal.source,
                confidence=float(getattr(claim, "confidence", 0.0) or proposal.confidence or 0.0),
                frame=int(getattr(claim, "frame", 0) or proposal.frame),
                evidence=_norm(getattr(claim, "evidence", "") or proposal.evidence),
                status=status,
            )
            prior = self._facts.get(key)

            if prior is None:
                if not proposed_value:
                    verdict.decisions.append(
                        CommitDecision(f"fact:{key}", "reject", "empty first reading", None, proposed_value, None)
                    )
                    continue
                self._facts[key] = incoming
                verdict.decisions.append(
                    CommitDecision(f"fact:{key}", "accept", incoming.source, None, proposed_value, proposed_value)
                )
                continue

            if prior.value == proposed_value:
                # Reinforcement: keep the more confident, most recent evidence.
                if incoming.confidence >= prior.confidence:
                    self._facts[key] = incoming
                verdict.decisions.append(
                    CommitDecision(f"fact:{key}", "unchanged", "reinforced", prior.value, proposed_value, prior.value)
                )
                continue

            if not proposed_value:
                # An empty reading does not erase a known fact, mirroring the
                # open_conversation wipe protection.
                verdict.decisions.append(
                    CommitDecision(f"fact:{key}", "reject", "empty reading does not erase a known fact", prior.value, proposed_value, prior.value)
                )
                continue

            # Genuine conflict: two non-empty values disagree. Record it, then
            # let the more confident reading win (ties go to the newer one).
            take_proposed = incoming.confidence >= prior.confidence
            resolution = "took_proposed" if take_proposed else "kept_prior"
            self._contradictions.append(
                Contradiction(
                    key=key,
                    prior=prior.value,
                    proposed=proposed_value,
                    prior_source=prior.source,
                    proposed_source=incoming.source,
                    frame=int(proposal.frame),
                    resolution=resolution,
                )
            )
            if len(self._contradictions) > MAX_CONTRADICTIONS:
                self._contradictions = self._contradictions[-MAX_CONTRADICTIONS:]
            if take_proposed:
                self._belief_flips += 1
                self._facts[key] = incoming
                verdict.decisions.append(
                    CommitDecision(f"fact:{key}", "accept", incoming.source, prior.value, proposed_value, proposed_value)
                )
            else:
                verdict.decisions.append(
                    CommitDecision(f"fact:{key}", "reject", "lower confidence than established belief", prior.value, proposed_value, prior.value)
                )

    def _commit_attempts(self, proposal: WorkspaceProposal, verdict: CommitVerdict) -> None:
        for attempt in proposal.attempts or []:
            if not (attempt.action or attempt.text or attempt.target):
                verdict.decisions.append(
                    CommitDecision("attempt", "reject", "empty attempt", None, attempt.to_dict(), None)
                )
                continue
            if self._attempts:
                last = self._attempts[-1]
                if last.identity() == attempt.identity() and last.outcome == attempt.outcome:
                    verdict.decisions.append(
                        CommitDecision(
                            "attempt",
                            "unchanged",
                            "identical to the previous attempt",
                            last.to_dict(),
                            attempt.to_dict(),
                            last.to_dict(),
                        )
                    )
                    continue
            self._attempts.append(attempt)
            verdict.decisions.append(
                CommitDecision("attempt", "accept", proposal.source, None, attempt.to_dict(), attempt.to_dict())
            )
        if len(self._attempts) > MAX_ATTEMPTS:
            self._attempts = self._attempts[-MAX_ATTEMPTS:]

    def _commit_transitions(self, proposal: WorkspaceProposal, verdict: CommitVerdict) -> None:
        for transition in proposal.transitions or []:
            self._transitions.append(transition)
            verdict.decisions.append(
                CommitDecision(
                    "transition",
                    "accept",
                    proposal.source,
                    None,
                    transition.to_dict(),
                    transition.to_dict(),
                )
            )
        if len(self._transitions) > MAX_TRANSITIONS:
            self._transitions = self._transitions[-MAX_TRANSITIONS:]

    def _commit_intent(self, proposal: WorkspaceProposal, verdict: CommitVerdict) -> None:
        if proposal.intent is None:
            return
        prior = self.intention.to_dict()
        self.intention = proposal.intent
        verdict.decisions.append(
            CommitDecision("intention", "accept", proposal.source, prior, proposal.intent.to_dict(), proposal.intent.to_dict())
        )

    def _commit_questions(self, proposal: WorkspaceProposal, verdict: CommitVerdict) -> None:
        for question in proposal.ask or []:
            raised = self.questions.ask(
                question.text,
                kind=question.kind,
                frame=question.raised_frame or self.frame,
                tested_by=question.tested_by[0] if question.tested_by else None,
            )
            if raised is not None:
                verdict.decisions.append(
                    CommitDecision("question", "accept", proposal.source, None, question.text, raised.id)
                )
        for hypothesis in proposal.hypotheses or []:
            self.questions.propose(
                hypothesis.statement,
                question_id=hypothesis.question_id,
                confidence=hypothesis.confidence,
                frame=hypothesis.raised_frame or self.frame,
            )
            verdict.decisions.append(
                CommitDecision("hypothesis", "accept", proposal.source, None, hypothesis.statement, None)
            )
        for gap in proposal.gaps or []:
            self.questions.declare_gap(
                gap.description,
                question_id=gap.question_id,
                blocking=gap.blocking,
                frame=gap.raised_frame or self.frame,
            )
            verdict.decisions.append(
                CommitDecision("gap", "accept", proposal.source, None, gap.description, None)
            )
        for text, answer, evidence in proposal.answers or []:
            resolved = self.questions.answer(text, answer, evidence=evidence)
            verdict.decisions.append(
                CommitDecision(
                    "answer",
                    "accept" if resolved is not None else "reject",
                    proposal.source,
                    text,
                    answer,
                    resolved.id if resolved is not None else None,
                )
            )
        for text, reason in proposal.abandon or []:
            dropped = self.questions.abandon(text, reason=reason)
            verdict.decisions.append(
                CommitDecision(
                    "abandon",
                    "accept" if dropped is not None else "reject",
                    proposal.source,
                    text,
                    reason,
                    dropped.id if dropped is not None else None,
                )
            )

    def _commit_budgets(self, proposal: WorkspaceProposal, verdict: CommitVerdict) -> None:
        if not proposal.budgets:
            return
        prior = self.budgets.to_dict()
        for key, value in proposal.budgets.items():
            if not hasattr(self.budgets, key):
                continue
            try:
                setattr(self.budgets, key, type(getattr(self.budgets, key))(value))
            except (TypeError, ValueError):
                continue
        verdict.decisions.append(
            CommitDecision("budgets", "accept", proposal.source, prior, dict(proposal.budgets), self.budgets.to_dict())
        )


def attempts_from_legacy(entries: Iterable[Any], *, kind: str = "search") -> List[AttemptRecord]:
    """Read the ``{"q", "outcome"}`` shape older code still writes."""
    out: List[AttemptRecord] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        out.append(
            AttemptRecord(
                kind=kind,
                action=str(entry.get("action") or kind),
                target=str(entry.get("target") or ""),
                text=str(entry.get("q") or entry.get("text") or ""),
                outcome=str(entry.get("outcome") or entry.get("result") or ""),
            )
        )
    return out
