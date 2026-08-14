"""Memory source adapters — scan(cursor) → ContactObservation batches.

Adapters know WhatsApp/Contacts; MemoryPipeline stays generic.

Day-0 rule: missing frequency evidence is better than fabricated frequency.
``unread_count`` is never mapped to interaction_count / active_days.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, Sequence

from plugin.agent.memory.pipeline import ContactObservation

logger = logging.getLogger(__name__)


class SourceScanDisposition(str, Enum):
    SUCCESS = "SUCCESS"
    UNAVAILABLE = "UNAVAILABLE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


@dataclass
class SourceObservationBatch:
    observations: list[ContactObservation] = field(default_factory=list)
    next_cursor: str = ""
    disposition: SourceScanDisposition = SourceScanDisposition.SUCCESS
    metadata: dict[str, Any] = field(default_factory=dict)


class MemorySourceAdapter(Protocol):
    source_name: str

    def scan(self, cursor: Optional[str] = None) -> SourceObservationBatch:
        ...


@dataclass
class FixtureSourceAdapter:
    """Test / synthetic Day-0 observations (may include true frequency counts)."""

    source_name: str = "fixture"
    observations: Sequence[ContactObservation] = field(default_factory=tuple)

    def scan(self, cursor: Optional[str] = None) -> SourceObservationBatch:
        if cursor:
            return SourceObservationBatch(
                observations=[],
                next_cursor=cursor,
                disposition=SourceScanDisposition.SUCCESS,
            )
        return SourceObservationBatch(
            observations=list(self.observations),
            next_cursor=f"{self.source_name}:done",
            disposition=SourceScanDisposition.SUCCESS,
        )


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class WhatsAppBridgeSourceAdapter:
    """Pull Day-0 contacts from Baileys bridge GET /contacts.

    Uses last_interaction_at when present. Leaves frequency/active_days unknown
    unless the bridge supplies real counts (not unreadCount).
    """

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
                logger.info("whatsapp bridge not connected; Day-0 AUTH_REQUIRED")
                return SourceObservationBatch(
                    observations=[],
                    next_cursor=cursor or "",
                    disposition=SourceScanDisposition.AUTH_REQUIRED,
                    metadata={"skipped": True, "http_status": 503},
                )
            return SourceObservationBatch(
                observations=[],
                next_cursor=cursor or "",
                disposition=SourceScanDisposition.ERROR,
                metadata={"error": str(exc), "http_status": exc.code},
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.info("whatsapp bridge unreachable for Day-0: %s", exc)
            return SourceObservationBatch(
                observations=[],
                next_cursor=cursor or "",
                disposition=SourceScanDisposition.UNAVAILABLE,
                metadata={"skipped": True, "error": str(exc)},
            )

        contacts = list(payload.get("contacts") or [])
        next_cursor = str(payload.get("cursor") or f"{self.source_name}:done")
        if cursor and cursor == next_cursor:
            return SourceObservationBatch(
                observations=[],
                next_cursor=next_cursor,
                disposition=SourceScanDisposition.SUCCESS,
            )

        observations: list[ContactObservation] = []
        for c in contacts:
            last_at = c.get("last_interaction_at")
            try:
                last_f = float(last_at) if last_at is not None else None
            except (TypeError, ValueError):
                last_f = None
            # Real counts only — never invent from unread_count / interaction_hint.
            c7 = _optional_int(c.get("interaction_count_7d"))
            c30 = _optional_int(c.get("interaction_count_30d"))
            c180 = _optional_int(c.get("interaction_count_180d"))
            active = _optional_int(c.get("active_days_30d"))
            unread = _optional_int(c.get("unread_count")) or 0
            observations.append(
                ContactObservation(
                    provider=str(c.get("provider") or "whatsapp"),
                    external_id=str(c.get("external_id") or ""),
                    display_name=str(c.get("display_name") or ""),
                    aliases=list(c.get("aliases") or []),
                    last_interaction_at=last_f,
                    interaction_count_7d=c7 if c7 is not None else 0,
                    interaction_count_30d=c30 if c30 is not None else 0,
                    interaction_count_180d=c180 if c180 is not None else 0,
                    active_days_30d=active if active is not None else 0,
                    frequency_known=c30 is not None or c7 is not None or c180 is not None,
                    metadata={
                        "source": c.get("source"),
                        "bridge": True,
                        "unread_count": unread,
                        "last_interaction_provenance": (
                            "whatsapp.chats.conversationTimestamp"
                            if last_f is not None
                            else "unknown"
                        ),
                    },
                )
            )
        return SourceObservationBatch(
            observations=observations,
            next_cursor=next_cursor,
            disposition=SourceScanDisposition.SUCCESS,
            metadata={"indexed": payload.get("indexed")},
        )
