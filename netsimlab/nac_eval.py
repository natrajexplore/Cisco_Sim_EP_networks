"""Lightweight local NAC policy evaluator.

This does NOT replace ISE. Scenarios pull the *real* policy building blocks
(authorization profiles, dACLs, SGTs, identity groups, portals) from the DevNet
ISE sandbox to prove behaviour and shape, then this evaluator resolves the
topology's declared intent policies against each endpoint so a decision can be
checked against the endpoint's ``expected_*`` fields - all with no RADIUS server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from netsimlab.topology.models import Endpoint, Policy, Topology

_GROUP_BY_KIND = {
    "workstation": "Employees",
    "byod": "Employees",
    "printer": "Printers",
    "phone": "IP-Phones",
    "iot": "IoT",
    "guest": "Guests",
    "ap": "Access-Points",
}


@dataclass
class Decision:
    endpoint: str
    mac: str
    auth_method: str
    matched_policy: str | None = None
    vlan: str | None = None
    sgt: str | None = None
    dacl: str | None = None
    url_redirect: str | None = None
    profile: str | None = None
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "mac": self.mac,
            "auth_method": self.auth_method,
            "matched_policy": self.matched_policy,
            "result": {
                "vlan": self.vlan,
                "sgt": self.sgt,
                "dacl": self.dacl,
                "url_redirect": self.url_redirect,
                "profile": self.profile,
            },
        }


def endpoint_facts(ep: Endpoint) -> dict[str, str]:
    facts: dict[str, str] = {
        "auth": ep.auth_method,
        "mac": ep.mac,
        "identity_group": _GROUP_BY_KIND.get(ep.kind, "Unknown"),
        "device_type": ep.kind,
    }
    facts.update(ep.attributes)
    if ep.auth_method == "guest":
        facts.setdefault("portal_state", "pre-auth")
    return facts


def _policy_matches(policy: Policy, facts: dict[str, str]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for key, want in policy.match.items():
        got = facts.get(key)
        if got is None:
            return False, [f"missing fact {key!r}"]
        if want.lower() in got.lower() or got.lower() == want.lower():
            reasons.append(f"{key}={got!r} ~ {want!r}")
        else:
            return False, [f"{key}={got!r} != {want!r}"]
    return True, reasons


def evaluate(topo: Topology, ep: Endpoint, kind: str = "authz") -> Decision:
    facts = endpoint_facts(ep)
    dec = Decision(endpoint=ep.name, mac=ep.mac, auth_method=ep.auth_method)
    for policy in topo.policies:
        if policy.kind != kind:
            continue
        matched, reasons = _policy_matches(policy, facts)
        if matched:
            dec.matched_policy = policy.name
            dec.vlan = policy.result.get("vlan")
            dec.sgt = policy.result.get("sgt")
            dec.dacl = policy.result.get("dacl")
            dec.url_redirect = policy.result.get("url_redirect")
            dec.profile = policy.result.get("logical_profile")
            dec.reasons = reasons
            return dec
    dec.reasons = ["no matching policy - default deny / no access"]
    return dec


def check_expectations(ep: Endpoint, dec: Decision) -> tuple[str, list[str]]:
    """Return (verdict, notes) comparing a decision to the endpoint's intent."""
    notes: list[str] = []
    verdict = "pass"
    if ep.expected_authz_profile and dec.matched_policy != ep.expected_authz_profile:
        verdict = "fail"
        notes.append(f"authz profile: got {dec.matched_policy!r}, expected {ep.expected_authz_profile!r}")
    if ep.expected_vlan is not None and str(ep.expected_vlan) != (dec.vlan or ""):
        verdict = "fail"
        notes.append(f"VLAN: got {dec.vlan!r}, expected {ep.expected_vlan}")
    if ep.expected_sgt and ep.expected_sgt != (dec.sgt or ""):
        # SGT mismatch is a warning if VLAN/profile already matched
        if verdict != "fail":
            verdict = "warn"
        notes.append(f"SGT: got {dec.sgt!r}, expected {ep.expected_sgt!r}")
    if verdict == "pass":
        notes.append(f"matched {dec.matched_policy!r} -> {dec.as_dict()['result']}")
    return verdict, notes
