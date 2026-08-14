"""Stable globally unique IDs for memory records."""

from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    """Return ``prefix:<uuid4-hex>`` suitable for multi-device sync later."""
    return f"{prefix}:{uuid.uuid4().hex}"


def event_id() -> str:
    return new_id("evt")


def episode_id() -> str:
    return new_id("ep")


def entity_id() -> str:
    return new_id("ent")


def source_identity_id() -> str:
    return new_id("sid")


def link_id() -> str:
    return new_id("lnk")


def relationship_id() -> str:
    return new_id("rel")


def aggregate_id() -> str:
    return new_id("agg")


def memory_id() -> str:
    return new_id("mem")


def derivation_id() -> str:
    return new_id("drv")
