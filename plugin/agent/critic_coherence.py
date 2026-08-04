"""The world critic's appeal court: judge a change the rules cannot account for.

The critic merges each perceptor reading into the carried document as a residual,
x + Δx: the prior survives by default and the delta must earn its way in. Between
two consecutive micro-actions the world cannot change radically unless an action
made it, so a radical delta with no action to explain it is more likely a misread
than a real screen.

Deterministic rules in :mod:`plugin.agent.world_critic` can tell *that* a change
is unaccounted for -- a whole object inventory replaced on an unchanged surface
with no viewport or filter action behind it. They cannot tell whether that
particular change makes sense, because that requires knowing what the action
meant and what the application plausibly does. That is the judgement this module
asks for.

It is deliberately an escalation and not a stage. Asking on every frame would add
a model call to a loop whose binding constraint is already latency, and the
overwhelming majority of frames drift by a row or two -- exactly the case the
rules settle for free. Absent this module the rules decide alone, which is the
behaviour every offline test and eval depends on.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

TIMEOUT_S = 45.0
MAX_LISTED = 12


def coherence_judge_enabled() -> bool:
    """Whether an unexplained change may be escalated to a model.

    Off by default in code: it costs a model call, and an offline test that
    silently reached for the network would be neither hermetic nor fast. Live
    launchers turn it on.
    """
    raw = os.getenv("HERMES_CRITIC_COHERENCE", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


_SYSTEM_PROMPT = (
    "You judge whether a change in a GUI agent's perception is coherent.\n\n"
    "The agent perceives a screen, acts, and perceives again. Between two "
    "consecutive actions the visible contents cannot change completely unless "
    "something caused it: the surface changed, the view scrolled, a filter was "
    "applied, or the application did something in response to the action.\n\n"
    "You are shown the previously accepted reading, the newly proposed reading, "
    "the action taken in between, and a summary of the difference. Decide whether "
    "the new reading is a believable consequence of that action.\n\n"
    "Answer with strict JSON only:\n"
    '{"explained": bool, "reason": str}\n\n'
    "explained true means the change makes sense and should be accepted. "
    "explained false means the new reading is more likely a misperception than a "
    "real change, and the previous reading should be kept.\n\n"
    "Be willing to say true. A screen that genuinely changed is common; refusing "
    "a real change strands the agent on a stale picture of a screen that has "
    "moved on, which is its own failure. Say false when the new reading has no "
    "plausible causal path from the action -- for instance an inventory of "
    "entirely different items after an action that only read the screen.\n\n"
    "reason is one short sentence naming the cause you accepted, or what is "
    "missing. It is written into the run log for a developer to read."
)


def _objects_brief(objects: Any, limit: int = MAX_LISTED) -> list:
    out = []
    for item in objects or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        kind = str(item.get("kind") or "").strip()
        out.append(f"{text[:60]}" + (f" [{kind}]" if kind else ""))
        if len(out) >= limit:
            break
    return out


def judge_inventory_rewrite(
    *,
    prior: Dict[str, Any],
    proposed: Dict[str, Any],
    delta: Any,
    surface: str,
    prior_surface: str,
    last_action: str,
    timeout_s: float = TIMEOUT_S,
) -> Tuple[bool, str]:
    """Judge one unexplained inventory rewrite. Returns (explained, reason).

    On any failure the change is *accepted* with the failure named. The judge is
    an appeal against a deterministic refusal, so an unavailable judge must leave
    the agent no worse off than before it existed -- and refusing a reading
    because a model call timed out would stall a run on an unrelated fault.
    """
    packet: Dict[str, Any] = {
        "action_taken": last_action or "none",
        "previous_reading": {
            "surface": prior_surface,
            "open_conversation": str(prior.get("open_conversation") or ""),
            "visible_items": _objects_brief(prior.get("objects")),
        },
        "proposed_reading": {
            "surface": surface,
            "open_conversation": str(proposed.get("open_conversation") or ""),
            "visible_items": _objects_brief(proposed.get("objects")),
        },
        "difference": {
            "kept": list(getattr(delta, "persisted", []) or [])[:MAX_LISTED],
            "new": list(getattr(delta, "appeared", []) or [])[:MAX_LISTED],
            "gone": list(getattr(delta, "disappeared", []) or [])[:MAX_LISTED],
            "fraction_of_old_gone": round(float(getattr(delta, "churn", 0.0)), 3),
            "fraction_of_new_unfamiliar": round(float(getattr(delta, "replacement", 0.0)), 3),
        },
        "surface_changed": bool(surface != prior_surface),
    }

    try:
        from plugin.agent.perception_synthesis import _call_llm_hard_timeout
        from plugin.agent.reasoning_consultation import consult_reasoning

        consultation = consult_reasoning(
            "perception",
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Judge this perception change.\n"
                    + json.dumps(packet, ensure_ascii=False, default=str)[:6000],
                },
            ],
            caller=lambda **kwargs: _call_llm_hard_timeout(timeout_s, **kwargs),
            call_kwargs={"task": "perception", "timeout": timeout_s},
            temperature=0.0,
            max_tokens=200,
        )
    except Exception as exc:
        logger.warning("critic coherence judge unavailable: %s", exc)
        return True, f"accepted unjudged: coherence judge unavailable ({exc})"

    parsed = getattr(consultation, "parsed", None)
    if not isinstance(parsed, dict):
        parsed = _loose_parse(getattr(consultation, "raw_response", "") or "")
    if not isinstance(parsed, dict) or "explained" not in parsed:
        return True, "accepted unjudged: coherence judge returned no verdict"

    explained = bool(parsed.get("explained"))
    reason = str(parsed.get("reason") or "").strip()[:180]
    verdict = "coherent" if explained else "incoherent"
    logger.info("Critic coherence judge: %s — %s", verdict, reason or "(no reason given)")
    return explained, reason or f"coherence judge found the change {verdict}"


_SURFACE_SYSTEM_PROMPT = (
    "You judge whether a GUI agent's screen-to-screen transition is believable.\n\n"
    "The agent was on one surface, took an action, and now reports being on "
    "another. A hand-written table of legal transitions could not account for "
    "this one, which means either the reading is wrong or the table is "
    "incomplete. Decide which.\n\n"
    "Answer with strict JSON only:\n"
    '{"explained": bool, "reason": str}\n\n'
    "explained true means the action plausibly leads from the old surface to the "
    "new one, and the table simply did not know about it. explained false means "
    "the new surface is not reachable that way and the reading should be "
    "discarded in favour of the previous surface.\n\n"
    "The table is a guess written by hand for one application, so do not defer to "
    "it. Judge the transition on whether the action could cause it. Applications "
    "also change surface on their own -- a call arrives, a dialog appears -- so an "
    "unrequested surface is not automatically wrong.\n\n"
    "reason is one short sentence, written into the run log for a developer."
)


def judge_surface_transition(
    *,
    prior_surface: str,
    proposed_surface: str,
    last_action: str,
    rule_reason: str = "",
    timeout_s: float = TIMEOUT_S,
) -> Tuple[bool, str]:
    """Judge a surface change the hand-written table refused.

    The table encodes one application's topology as literal strings, so its
    refusals conflate "this cannot happen" with "nobody wrote this edge down".
    Only the second kind is a bug, and it is the kind that discards a correct
    reading. On any failure the refusal stands, since that is the behaviour the
    table had on its own.
    """
    packet = {
        "previous_surface": prior_surface,
        "reported_surface": proposed_surface,
        "action_taken": last_action or "none",
        "why_the_table_refused": rule_reason,
    }
    try:
        from plugin.agent.perception_synthesis import _call_llm_hard_timeout
        from plugin.agent.reasoning_consultation import consult_reasoning

        consultation = consult_reasoning(
            "perception",
            [
                {"role": "system", "content": _SURFACE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Judge this transition.\n"
                    + json.dumps(packet, ensure_ascii=False, default=str)[:2000],
                },
            ],
            caller=lambda **kwargs: _call_llm_hard_timeout(timeout_s, **kwargs),
            call_kwargs={"task": "perception", "timeout": timeout_s},
            temperature=0.0,
            max_tokens=200,
        )
    except Exception as exc:
        logger.warning("critic surface judge unavailable: %s", exc)
        return False, rule_reason or f"surface judge unavailable ({exc})"

    parsed = getattr(consultation, "parsed", None)
    if not isinstance(parsed, dict):
        parsed = _loose_parse(getattr(consultation, "raw_response", "") or "")
    if not isinstance(parsed, dict) or "explained" not in parsed:
        return False, rule_reason or "surface judge returned no verdict"

    explained = bool(parsed.get("explained"))
    reason = str(parsed.get("reason") or "").strip()[:180]
    logger.info(
        "Critic surface judge: %s->%s %s — %s",
        prior_surface,
        proposed_surface,
        "allowed" if explained else "refused",
        reason or "(no reason given)",
    )
    return explained, reason or f"surface judge {'allowed' if explained else 'refused'} the jump"


def surface_judge_for_critic() -> Optional[Any]:
    """The surface judge ``critique_world_proposal`` expects, or None if off."""
    if not coherence_judge_enabled():
        return None

    def _judge(
        *,
        prior_surface: str,
        proposed_surface: str,
        last_action: str,
        rule_reason: str = "",
    ) -> Tuple[bool, str]:
        return judge_surface_transition(
            prior_surface=prior_surface,
            proposed_surface=proposed_surface,
            last_action=last_action,
            rule_reason=rule_reason,
        )

    return _judge


def _loose_parse(raw: str) -> Optional[Dict[str, Any]]:
    """Pull the JSON object out of a reply that wrapped it in prose."""
    text = str(raw or "").strip()
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def judge_for_critic() -> Optional[Any]:
    """The judge callable ``critique_world_proposal`` expects, or None if off."""
    if not coherence_judge_enabled():
        return None

    def _judge(
        *,
        prior: Dict[str, Any],
        proposed: Dict[str, Any],
        delta: Any,
        surface: str,
        prior_surface: str,
        last_action: str,
    ) -> Tuple[bool, str]:
        return judge_inventory_rewrite(
            prior=prior,
            proposed=proposed,
            delta=delta,
            surface=surface,
            prior_surface=prior_surface,
            last_action=last_action,
        )

    return _judge
