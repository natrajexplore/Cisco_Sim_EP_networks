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


# --- IOS running-config parsing -------------------------------------------

def running_config_text(payload: Any) -> str:
    """Pull the CLI text out of a Catalyst Center ``/config`` response."""
    body = dnac_response(payload)
    if isinstance(body, str):
        return body
    if isinstance(body, dict):
        for k in ("runningConfig", "config", "cliConfig"):
            if isinstance(body.get(k), str):
                return body[k]
    if isinstance(body, list) and body and isinstance(body[0], dict):
        for k in ("runningConfig", "config"):
            if isinstance(body[0].get(k), str):
                return body[0][k]
    return ""


def interface_block(config_text: str, ifname: str) -> str:
    """Return the ``interface <ifname>`` stanza (without the header line).

    Matches on a normalised name so ``Gi1/0/10`` finds ``GigabitEthernet1/0/10``.
    """
    want = _norm_if(ifname)
    lines = config_text.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("interface "):
            capturing = _norm_if(stripped.split(None, 1)[1]) == want
            continue
        if capturing:
            if line and not line[0].isspace() and stripped != "!":
                break
            if stripped in ("", "!"):
                if out:
                    break
                continue
            out.append(stripped)
    return "\n".join(out)


def nac_config_flags(block: str) -> dict[str, Any]:
    """Best-effort read of the NAC-relevant lines in an interface stanza."""
    lines = [ln.strip().lower() for ln in block.splitlines()]
    b = "\n".join(lines)
    host = next(
        (hm for hm in ("multi-domain", "multi-auth", "multi-host", "single-host")
         if f"host-mode {hm}" in b),
        None,
    )
    if "authentication open" in b:
        mode = "open"
    elif "access-session closed" in b:
        mode = "closed"
    else:
        mode = "closed"  # IBNS default when 'authentication open' is absent
    return {
        "dot1x": "dot1x pae authenticator" in b,
        "mab": any(ln == "mab" or ln.startswith("mab ") for ln in lines),
        "port_control_auto": "port-control auto" in b,
        "host_mode": host,
        "order": "mab-first" if "authentication order mab" in b or "order mab dot1x" in b
        else "dot1x-first",
        "reauth": "authentication periodic" in b or "dot1x reauthentication" in b,
        "mode": mode,
        "voice_vlan": "switchport voice vlan" in b,
        "device_tracking": "ip device tracking" in b or "device-tracking attach-policy" in b,
    }


def _norm_if(name: str) -> str:
    name = name.strip().lower()
    for long, short in (
        ("tengigabitethernet", "te"), ("fortygigabitethernet", "fo"),
        ("hundredgige", "hu"), ("twentyfivegige", "twe"),
        ("gigabitethernet", "gi"), ("fastethernet", "fa"),
        ("appgigabitethernet", "ap"), ("ethernet", "et"),
    ):
        if name.startswith(long):
            return short + name[len(long):]
    return name
