"""Local NAC / AP switchport configuration checker.

Evaluates an :class:`AccessPort` (the *intended* config) against Cisco NAC and
wireless access-port best practice. No device is contacted - the
``access_port_nac_validation`` scenario optionally cross-checks the findings
against a real running-config pulled from Catalyst Center.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from netsimlab.topology.models import AccessPort, Endpoint

Severity = Literal["crit", "warn", "info"]

# endpoint kinds that cannot do 802.1X and therefore need a MAB fallback
_NON_SUPPLICANT = {"printer", "iot", "phone"}


@dataclass
class PortFinding:
    severity: Severity
    code: str
    message: str

    def as_note(self) -> str:
        return f"[{self.severity.upper()}] {self.code}: {self.message}"


def verdict_for(findings: list[PortFinding]) -> str:
    if any(f.severity == "crit" for f in findings):
        return "fail"
    if any(f.severity == "warn" for f in findings):
        return "warn"
    return "pass"


def evaluate_nac_port(port: AccessPort, endpoint: Endpoint | None = None) -> list[PortFinding]:
    f: list[PortFinding] = []

    if port.trunk:
        f.append(PortFinding("crit", "nac-on-trunk",
                             "NAC configured on a trunk port - 802.1X applies to access ports only"))

    methods = set(port.methods)
    if not methods & {"dot1x", "mab", "webauth"}:
        f.append(PortFinding("crit", "no-auth-method",
                             "no authentication method (dot1x / mab / webauth) on the port"))

    if port.mode == "open":
        f.append(PortFinding("warn", "open-mode",
                             "open authentication: all traffic passes before/without auth - "
                             "use 'closed' or 'low-impact'"))
    elif port.mode == "monitor":
        f.append(PortFinding("info", "monitor-mode",
                             "monitor mode: authentication is logged but never enforced"))

    if port.host_mode == "multi-host":
        f.append(PortFinding("warn", "multi-host",
                             "multi-host authorises the port after the first success - "
                             "prefer multi-auth so every MAC is authenticated"))
    if port.host_mode == "single-host" and port.voice_vlan is not None:
        f.append(PortFinding("crit", "single-host-voice",
                             "single-host with a voice VLAN: the phone and the PC behind it "
                             "cannot both authenticate - use multi-domain"))
    if port.voice_vlan is not None and port.host_mode not in {"multi-domain", "multi-auth"}:
        f.append(PortFinding("warn", "voice-host-mode",
                             f"voice VLAN with host-mode {port.host_mode!r}; multi-domain is expected"))

    if not port.coa:
        f.append(PortFinding("crit", "no-coa",
                             "CoA disabled: ISE cannot re-authorise (VLAN change, quarantine, "
                             "posture remediation) after the session is up"))
    if not port.reauth:
        f.append(PortFinding("warn", "no-reauth",
                             "no periodic re-authentication - stale sessions persist across "
                             "policy changes"))
    if not port.dacl:
        f.append(PortFinding("warn", "no-dacl",
                             "downloadable ACLs not supported on the port (needs IP device "
                             "tracking / 'ip access-list' pre-auth) - dynamic ACL policy will not apply"))

    if "dot1x" not in methods and "mab" in methods:
        f.append(PortFinding("info", "mab-only",
                             "MAB only: no 802.1X - acceptable for fixed IoT, weak for user ports"))
    if port.order == "mab-first":
        f.append(PortFinding("info", "mab-first",
                             "MAB precedes 802.1X - only intended for IoT-dense ports; a rogue "
                             "MAC authorises before the supplicant is tried"))

    if endpoint is not None:
        if endpoint.auth_method == "dot1x" and "dot1x" not in methods:
            f.append(PortFinding("crit", "supplicant-no-dot1x",
                                 f"{endpoint.name!r} authenticates with 802.1X but the port has no 'dot1x'"))
        if endpoint.kind in _NON_SUPPLICANT and "mab" not in methods:
            f.append(PortFinding("warn", "no-mab-fallback",
                                 f"{endpoint.name!r} ({endpoint.kind}) cannot do 802.1X and the port "
                                 f"has no MAB fallback"))
        if endpoint.expected_vlan is not None and port.data_vlan not in (None, endpoint.expected_vlan):
            f.append(PortFinding("warn", "vlan-mismatch",
                                 f"port data VLAN {port.data_vlan} != endpoint expected VLAN "
                                 f"{endpoint.expected_vlan} (dynamic VLAN should still override)"))

    return f


def evaluate_ap_port(port: AccessPort) -> list[PortFinding]:
    f: list[PortFinding] = []

    if not port.poe:
        f.append(PortFinding("warn", "no-poe",
                             "PoE disabled on an AP port - the AP will not power up unless "
                             "externally powered"))
    if port.qos_trust == "none":
        f.append(PortFinding("warn", "no-qos-trust",
                             "no QoS trust: the AP's CoS/DSCP markings (voice, video) are "
                             "rewritten to 0 at ingress"))
    if port.methods:
        f.append(PortFinding("info", "ap-port-dot1x",
                             "authentication configured on an AP port - ensure MAB + host-mode "
                             "multi-host or the CAPWAP tunnel and client traffic will be dropped"))
    if not port.trunk and port.data_vlan is None:
        f.append(PortFinding("warn", "ap-access-no-vlan",
                             "AP access port with no VLAN assigned"))
    if port.trunk and not port.trunk_allowed_vlans:
        f.append(PortFinding("info", "trunk-no-allowed-list",
                             "trunk with no explicit allowed-VLAN list - prune to the AP's "
                             "management + client VLANs"))
    return f


def evaluate_uplink_port(port: AccessPort) -> list[PortFinding]:
    f: list[PortFinding] = []
    if not port.trunk:
        f.append(PortFinding("warn", "uplink-not-trunk",
                             "switch-to-switch uplink is not a trunk"))
    if port.methods:
        f.append(PortFinding("crit", "nac-on-uplink",
                             "authentication configured on an infrastructure uplink"))
    return f


def evaluate_port(port: AccessPort, endpoint: Endpoint | None = None) -> list[PortFinding]:
    if port.purpose == "ap":
        return evaluate_ap_port(port)
    if port.purpose == "uplink":
        return evaluate_uplink_port(port)
    return evaluate_nac_port(port, endpoint)
