"""Deterministic ReferenceInterpreter — no LLM in the closed loop."""

from __future__ import annotations

import re
from typing import Optional

from plugin.agent.reference.types import Reference
from plugin.worldmodel.entities.normalize import _clean_label

_TYPE_WORDS = {
    "group": "group",
    "groups": "group",
    "community": "community",
    "communities": "community",
    "contact": "contact",
    "chat": "contact",
}


def _title_case_name(s: str) -> str:
    s = _clean_label(s)
    if not s:
        return ""
    # Preserve existing casing if mixed; else title-case tokens
    if any(c.isupper() for c in s) and any(c.islower() for c in s):
        return s
    return " ".join(t[:1].upper() + t[1:].lower() if t else "" for t in s.split())


class ReferenceInterpreter:
    """
    "now group" → Reference(name="Now", kind=group, hypotheses=["Now", "Now Group", ...])
    "plugin support" → Reference(name="plugin support", kind=contact)
    """

    def interpret(
        self,
        raw: str,
        *,
        kind: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Reference:
        cleaned = _clean_label(raw or "")
        if not cleaned:
            return Reference(raw=raw or "", name="", kind="unknown", confidence=0.0)

        # Explicit override from Hermes/LLM (outside closed loop)
        if kind and name:
            k = str(kind).lower().strip()
            n = _title_case_name(name) if k == "group" else _clean_label(name)
            hyps = self._hypotheses(n, k, cleaned)
            return Reference(raw=cleaned, name=n, kind=k, confidence=0.95, search_hypotheses=hyps)
        if kind and not name:
            k = str(kind).lower().strip()
            n = self._strip_type_word(cleaned, k) or cleaned
            n = _title_case_name(n) if k in {"group", "community"} else n
            return Reference(
                raw=cleaned,
                name=n,
                kind=k,
                confidence=0.9,
                search_hypotheses=self._hypotheses(n, k, cleaned),
            )

        tokens = cleaned.lower().split()
        inferred_kind = "contact"
        conf = 0.75
        name_out = cleaned

        # Type word at end or as separate token: "now group", "engineering group"
        if len(tokens) >= 2 and tokens[-1] in _TYPE_WORDS:
            inferred_kind = _TYPE_WORDS[tokens[-1]]
            name_out = _clean_label(" ".join(cleaned.split()[:-1]))
            conf = 0.88
        elif len(tokens) >= 2 and tokens[0] in {"group", "community"}:
            # "group now" unusual but handle
            inferred_kind = _TYPE_WORDS[tokens[0]]
            name_out = _clean_label(" ".join(cleaned.split()[1:]))
            conf = 0.8
        elif re.search(r"\bcommunity\b", cleaned, re.I):
            inferred_kind = "community"
            name_out = self._strip_type_word(cleaned, "community") or cleaned
            conf = 0.85
        elif re.search(r"\bgroups?\b", cleaned, re.I):
            inferred_kind = "group"
            name_out = self._strip_type_word(cleaned, "group") or cleaned
            conf = 0.85

        if inferred_kind in {"group", "community"}:
            name_out = _title_case_name(name_out)
        else:
            name_out = _clean_label(name_out)

        return Reference(
            raw=cleaned,
            name=name_out or cleaned,
            kind=inferred_kind,
            confidence=conf,
            search_hypotheses=self._hypotheses(name_out or cleaned, inferred_kind, cleaned),
        )

    def _strip_type_word(self, text: str, kind: str) -> str:
        words = {
            "group": r"\bgroups?\b",
            "community": r"\bcommunities?\b",
            "contact": r"\bcontacts?\b",
        }
        pat = words.get(kind, "")
        if not pat:
            return text
        return _clean_label(re.sub(pat, " ", text, flags=re.I))

    def _hypotheses(self, name: str, kind: str, raw: str) -> list:
        out: list = []
        n = _clean_label(name)
        r = _clean_label(raw)
        if n:
            out.append(n)
        if kind == "group" and n:
            g = f"{n} Group"
            if g.lower() not in {x.lower() for x in out}:
                out.append(g)
            # Truncation-friendly stem already is n
        if kind == "community" and n:
            c = f"{n} Community"
            if c.lower() not in {x.lower() for x in out}:
                out.append(c)
        if r and r.lower() not in {x.lower() for x in out}:
            out.append(r)
        return out


_DEFAULT: Optional[ReferenceInterpreter] = None


def get_reference_interpreter() -> ReferenceInterpreter:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = ReferenceInterpreter()
    return _DEFAULT


def interpret_reference(
    raw: str,
    *,
    kind: Optional[str] = None,
    name: Optional[str] = None,
) -> Reference:
    return get_reference_interpreter().interpret(raw, kind=kind, name=name)
