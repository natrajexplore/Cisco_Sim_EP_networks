"""Scenario: access-port NAC + AP-port configuration validation.

Real-world mapping
------------------
Before ISE can enforce anything, the *switchport* has to be built correctly: the
right host-mode, 802.1X + MAB, closed/low-impact mode, CoA, downloadable-ACL
support, periodic re-auth - and AP uplink ports need PoE, a trunk/allowed-VLAN
list and QoS trust rather than NAC. This scenario evaluates every access-layer
port in the topology intent against those rules and, when Catalyst Center is
reachable, cross-checks the findings against a real switch running-config.
"""

from __future__ import annotations

from typing import Iterator

from netsimlab import port_eval
from netsimlab.apiutil import interface_block, nac_config_flags, running_config_text
from netsimlab.connectors.catalyst_center import CatalystCenterConnector
from netsimlab.scenarios.base import Scenario, ScenarioContext, StepResult


class AccessPortNacValidation(Scenario):
    name = "access_port_nac_validation"
    title = "Access port NAC + AP port configuration"
    description = "Verify 802.1X/MAB/CoA/host-mode on NAC ports and PoE/trunk/QoS on AP ports."
    requires = ("catalyst_center",)

    def steps(self, ctx: ScenarioContext) -> Iterator[StepResult]:
        topo = ctx.topology
        ports = topo.effective_access_ports()
        ep_by_port = {
            (e.connects_to, e.port): e for e in topo.endpoints if e.port
        }

        by_purpose = {"nac": 0, "ap": 0, "uplink": 0}
        for p in ports:
            by_purpose[p.purpose] = by_purpose.get(p.purpose, 0) + 1
        yield StepResult(
            name="Enumerate access-layer ports (topology intent)",
            verdict="pass" if ports else "warn",
            summary=(
                f"{len(ports)} port(s): {by_purpose['nac']} NAC, "
                f"{by_purpose['ap']} AP, {by_purpose['uplink']} uplink"
            ),
            data={"ports": [f"{p.switch} {p.interface} ({p.purpose})" for p in ports]},
        )

        crit = warn = 0
        for p in ports:
            ep = ep_by_port.get(p.key)
            findings = port_eval.evaluate_port(p, ep)
            verdict = port_eval.verdict_for(findings)
            n_crit = sum(1 for f in findings if f.severity == "crit")
            crit += n_crit
            warn += sum(1 for f in findings if f.severity == "warn")
            label = {"nac": "NAC port", "ap": "AP port", "uplink": "uplink"}[p.purpose]
            yield StepResult(
                name=f"{label}: {p.switch} {p.interface}" + (f" -> {ep.name}" if ep else ""),
                verdict=verdict,
                request=_describe(p),
                summary=(
                    "config matches best practice"
                    if not findings
                    else f"{len(findings)} finding(s)"
                    + (f", {n_crit} critical" if n_crit else "")
                ),
                notes=[f.as_note() for f in findings] or ["no issues"],
                data={"port": p.model_dump(), "findings": [f.__dict__ for f in findings]},
            )

        # ---- optional live cross-check against a real switch running-config ----
        dnac = CatalystCenterConnector(mode=ctx.mode, scenario=self.name)
        try:
            with dnac.session() as d:
                sw_id = d.first_switch_id()
                cfg = running_config_text(d.device_running_config(sw_id)) if sw_id else ""
            if not cfg:
                raise RuntimeError("no running-config returned")
            nac_ifaces = _nac_interfaces(cfg)
            first_flags = nac_config_flags(nac_ifaces[0][1]) if nac_ifaces else {}
            # if our topology's sample interface exists on this switch, parse it too
            sample = next((p for p in ports if p.purpose == "nac"), None)
            sample_block = interface_block(cfg, sample.interface) if sample else ""
            yield StepResult(
                name="Cross-check against Catalyst Center switch running-config",
                verdict="pass" if nac_ifaces else "info",
                request=f"GET /dna/intent/api/v1/network-device/{sw_id}/config",
                summary=(
                    f"pulled {len(cfg.splitlines())}-line running-config; "
                    + (
                        f"{len(nac_ifaces)} interface(s) carry NAC config "
                        f"(e.g. {nac_ifaces[0][0]}: {_flag_summary(first_flags)})"
                        if nac_ifaces
                        else "this device has no 802.1X/MAB interfaces - intent checks above stand alone"
                    )
                    + (
                        f"; topology interface {sample.interface}: {_flag_summary(nac_config_flags(sample_block))}"
                        if sample_block
                        else ""
                    )
                ),
                data={
                    "switch_id": sw_id,
                    "nac_interface_count": len(nac_ifaces),
                    "sample_parsed": nac_config_flags(nac_ifaces[0][1]) if nac_ifaces else {},
                },
            )
        except Exception as exc:  # noqa: BLE001
            yield StepResult(
                name="Cross-check against Catalyst Center switch running-config",
                verdict="info",
                summary=f"live config cross-check unavailable ({exc}); intent checks above stand alone",
            )

        yield StepResult(
            name="Access-port validation summary",
            verdict="fail" if crit else ("warn" if warn else "pass"),
            summary=f"{crit} critical, {warn} warning(s) across {len(ports)} port(s)",
            notes=[
                "Critical = ISE enforcement will not work as intended on that port.",
                "Warning = weaker security posture or operational risk.",
            ],
        )


def _describe(p) -> str:
    if p.purpose == "ap":
        return (f"{'trunk' if p.trunk else 'access'} poe={'on' if p.poe else 'off'} "
                f"qos-trust={p.qos_trust} vlans={p.trunk_allowed_vlans or p.data_vlan}")
    if p.purpose == "uplink":
        return f"{'trunk' if p.trunk else 'access'} infrastructure uplink"
    return (f"mode={p.mode} host-mode={p.host_mode} methods={'+'.join(p.methods) or 'none'} "
            f"order={p.order} reauth={p.reauth} coa={p.coa} dacl={p.dacl}"
            + (f" voice-vlan={p.voice_vlan}" if p.voice_vlan else ""))


def _flag_summary(flags: dict) -> str:
    on = [k for k, v in flags.items() if v is True]
    return ", ".join(on) if on else "no NAC lines found"


def _nac_interfaces(cfg: str) -> list[tuple[str, str]]:
    """Every ``interface`` stanza in a running-config that carries NAC config."""
    out: list[tuple[str, str]] = []
    name: str | None = None
    body: list[str] = []
    for line in cfg.splitlines():
        if line.startswith("interface "):
            if name and _has_nac("\n".join(body)):
                out.append((name, "\n".join(body)))
            name, body = line.split(None, 1)[1].strip(), []
        elif name and (line.startswith(" ") or line.strip() == "!"):
            if line.strip() == "!":
                if name and _has_nac("\n".join(body)):
                    out.append((name, "\n".join(body)))
                name, body = None, []
            else:
                body.append(line.strip())
        else:
            if name and _has_nac("\n".join(body)):
                out.append((name, "\n".join(body)))
            name, body = None, []
    if name and _has_nac("\n".join(body)):
        out.append((name, "\n".join(body)))
    return out


def _has_nac(block: str) -> bool:
    b = block.lower()
    return any(k in b for k in ("dot1x pae", "\nmab", "access-session", "authentication port-control"))
