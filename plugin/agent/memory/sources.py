"""Memory source adapters — scan(cursor) → ContactObservation batches.

Adapters know WhatsApp/Contacts; MemoryPipeline stays generic.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Sequence

from plugin.agent.memory.pipeline import ContactObservation

logger = logging.getLogger(__name__)


@dataclass
class SourceObservationBatch:
    observations: list[ContactObservation] = field(default_factory=list)
    next_cursor: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class MemorySourceAdapter(Protocol):
    source_name: str

    def scan(self, cursor: Optional[str] = None) -> SourceObservationBatch:
        ...


@dataclass
class FixtureSourceAdapter:
    """Test / synthetic Day-0 observations."""

    source_name: str = "fixture"
    observations: Sequence[ContactObservation] = field(default_factory=tuple)

    def scan(self, cursor: Optional[str] = None) -> SourceObservationBatch:
        if cursor:
            return SourceObservationBatch(observations=[], next_cursor=cursor)
        return SourceObservationBatch(
            observations=list(self.observations),
            next_cursor=f"{self.source_name}:done",
        )


@dataclass
class WhatsAppBridgeSourceAdapter:
    """Pull Day-0 contact + interaction hints from Baileys bridge GET /contacts."""

    source_name: str = "whatsapp_bridge"
    base_url: str = "http://127.0.0.1:3000"
    timeout_s: float = 3.0

    def scan(self, cursor: Optional[str] = None) -> SourceObservationBatch:
        url = f"{self.base_url.rstrip('/')}/contacts"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                logger.info("whatsapp bridge not connected; skip Day-0 scan")
                return SourceObservationBatch(
                    observations=[], next_cursor=cursor or "", metadata={"skipped": True}
                )
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.info("whatsapp bridge unreachable for Day-0: %s", exc)
            return SourceObservationBatch(
                observations=[], next_cursor=cursor or "", metadata={"skipped": True}
            )

        contacts = list(payload.get("contacts") or [])
        next_cursor = str(payload.get("cursor") or f"{self.source_name}:done")
        # Idempotent: if cursor unchanged and we already ingested, return empty
        if cursor and cursor == next_cursor:
            return SourceObservationBatch(observations=[], next_cursor=next_cursor)

        observations: list[ContactObservation] = []
        for c in contacts:
            last_at = c.get("last_interaction_at")
            try:
                last_f = float(last_at) if last_at is not None else None
            except (TypeError, ValueError):
                last_f = None
            hint = int(c.get("interaction_hint") or 0)
            # Map sparse bridge hints into aggregate windows without inventing history.
            count_30d = max(hint, 1 if last_f else 0)
            observations.append(
                ContactObservation(
                    provider=str(c.get("provider") or "whatsapp"),
                    external_id=str(c.get("external_id") or ""),
                    display_name=str(c.get("display_name") or ""),
                    aliases=list(c.get("aliases") or []),
                    last_interaction_at=last_f,
                    interaction_count_7d=min(count_30d, hint or count_30d),
                    interaction_count_30d=count_30d,
                    interaction_count_180d=count_30d,
                    active_days_30d=min(30, max(0, hint)),
                    metadata={"source": c.get("source"), "bridge": True},
                )
            )
        return SourceObservationBatch(
            observations=observations,
            next_cursor=next_cursor,
            metadata={"indexed": payload.get("indexed")},
        )
