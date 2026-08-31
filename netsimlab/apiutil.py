"""Helpers to normalise Cisco API response envelopes."""

from __future__ import annotations

from typing import Any


def ise_resources(payload: Any) -> list[dict[str, Any]]:
    """ERS list responses look like {"SearchResult": {"total": N, "resources": [...]}}."""
    if isinstance(payload, dict):
        sr = payload.get("SearchResult")
        if isinstance(sr, dict):
            return list(sr.get("resources", []))
    if isinstance(payload, list):
        return payload
    return []


def ise_total(payload: Any) -> int:
    if isinstance(payload, dict):
        sr = payload.get("SearchResult")
        if isinstance(sr, dict) and "total" in sr:
            return int(sr["total"])
    return len(ise_resources(payload))


def dnac_response(payload: Any) -> Any:
    """Intent-API responses usually wrap the useful bit under "response"."""
    if isinstance(payload, dict) and "response" in payload:
        return payload["response"]
    return payload


def names(items: list[dict[str, Any]], key: str = "name") -> list[str]:
    out = []
    for it in items:
        if isinstance(it, dict) and it.get(key):
            out.append(str(it[key]))
    return sorted(out)
