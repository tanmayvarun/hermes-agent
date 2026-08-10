"""Storage effect → method adapter (safe reclaim policy)."""

from __future__ import annotations

from typing import Dict, List

from plugin.agent.executive.blocking import ResolvedMethod

STORAGE_EFFECT_METHODS: Dict[str, List[ResolvedMethod]] = {
    "storage:available_bytes_at_least": [
        ResolvedMethod(
            capability="relieve_host_storage",
            applicable_if="agent_owned_reclaimable_bytes > 0",
            effect_key="storage:available_bytes_at_least",
        )
    ],
    "app_operational:is_true": [
        ResolvedMethod(
            capability="recover_blocked_app",
            applicable_if="blocked_app_recoverable",
            effect_key="app_operational:is_true",
        )
    ],
}
