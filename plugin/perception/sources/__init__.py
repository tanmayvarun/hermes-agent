"""Perception source registry."""

from __future__ import annotations

from typing import Dict, List

from plugin.perception.sources.base import PerceptionSource
from plugin.perception.sources.macapptree import MacAppTreeSource
from plugin.perception.sources.pyobjc_ax import PyObjcAxSource


def default_sources(*, with_screenshot: bool = False, with_vision: bool = False) -> List[PerceptionSource]:
    out: List[PerceptionSource] = [PyObjcAxSource()]
    try:
        out.append(MacAppTreeSource(with_screenshot=with_screenshot))
    except Exception:
        pass
    if with_vision or with_screenshot:
        try:
            from plugin.perception.sources.screen2ax import Screen2AxSource

            out.append(Screen2AxSource())
        except Exception:
            pass
    return out


def sources_by_id() -> Dict[str, PerceptionSource]:
    return {s.source_id: s for s in default_sources()}
