"""Device access inventory + quality scoring for the dashboard.

Joins the topology intent (devices, links, endpoints, effective access ports)
with the local port checker so every device carries its switchports, attached
endpoints, neighbors, findings and a 0-100 health score. Nothing here talks to
a controller.
"""

from __future__ import annotations

from typing import Any

from netsimlab import port_eval
from netsimlab.topology.graph import build_graph, validate
from netsimlab.topology.models import Topology

# vertical tier used to layer the 3D topology (higher = closer to the top)
ROLE_TIER = {
    "catalyst_center": 5, "ise": 5,
    "firewall": 4, "border": 4, "core": 4,
    "distribution": 3, "wlc": 3,
    "access": 2, "ssid": 1, "ap": 1,
    "endpoint": 0,
}

# score penalty per finding severity
_PENALTY = {"crit": 25, "warn": 8, "info": 0}


def health_grade(score: int) -> str:
    if score >= 90:
        return "good"
    if score >= 70:
        return "fair"
    return "poor"


def _score(findings: list[dict[str, Any]]) -> int:
    return max(0, 100 - sum(_PENALTY.get(f["severity"], 0) for f in findings))


def device_inventory(topo: Topology) -> list[dict[str, Any]]:
    g = build_graph(topo)
    ep_by_port = {(e.connects_to, e.port): e for e in topo.endpoints if e.port}

    ports_by_switch: dict[str, list[dict[str, Any]]] = {}
    for p in topo.effective_access_ports():
        ep = ep_by_port.get(p.key)
        raw = port_eval.evaluate_port(p, ep)
        findings = [f.__dict__ for f in raw]
        ports_by_switch.setdefault(p.switch, []).append(
            {
                "interface": p.interface,
                "purpose": p.purpose,
                "mode": p.mode if p.purpose == "nac" else None,
                "host_mode": p.host_mode if p.purpose == "nac" else None,
                "methods": list(p.methods),
                "order": p.order if p.methods else None,
                "data_vlan": p.data_vlan,
                "voice_vlan": p.voice_vlan,
                "trunk": p.trunk,
                "trunk_allowed_vlans": list(p.trunk_allowed_vlans),
                "poe": p.poe,
                "qos_trust": p.qos_trust,
                "coa": p.coa,
                "reauth": p.reauth,
                "dacl": p.dacl,
                "endpoint": ep.name if ep else None,
                "verdict": port_eval.verdict_for(raw),
                "findings": findings,
            }
        )

    out = []
    for d in topo.devices:
        ports = ports_by_switch.get(d.name, [])
        findings = [
            {**f, "interface": p["interface"]} for p in ports for f in p["findings"]
        ]
        if d.role == "ap" and not d.wlc:
            findings.append({"severity": "crit", "code": "ap-no-wlc",
                             "message": "AP has no WLC", "interface": None})
        if d.role not in {"ap"} and not d.mgmt_ip:
            findings.append({"severity": "info", "code": "no-mgmt-ip",
                             "message": "no management IP in the topology", "interface": None})

        neighbors = []
        for nb in g.neighbors(d.name):
            data = g.edges[d.name, nb]
            ports_map = data.get("ports") or {}
            neighbors.append(
                {
                    "name": nb,
                    "kind": g.nodes[nb].get("kind"),
                    "role": g.nodes[nb].get("role"),
                    "link": data.get("kind"),
                    "local_port": ports_map.get(d.name),
                    "remote_port": ports_map.get(nb),
                    "vlan": data.get("access_vlan"),
                }
            )
        neighbors.sort(key=lambda n: (n["local_port"] or "~", n["name"]))

        endpoints = [
            {
                "name": e.name, "mac": e.mac, "kind": e.kind, "port": e.port,
                "auth_method": e.auth_method, "identity": e.identity,
                "expected_vlan": e.expected_vlan, "expected_sgt": e.expected_sgt,
                "expected_authz_profile": e.expected_authz_profile,
            }
            for e in topo.endpoints if e.connects_to == d.name
        ]

        score = _score(findings)
        out.append(
            {
                "name": d.name,
                "role": d.role,
                "platform": d.platform,
                "mgmt_ip": d.mgmt_ip,
                "site": d.site.path() if d.site else None,
                "wlc": d.wlc,
                "tier": ROLE_TIER.get(d.role, 2),
                "ports": ports,
                "endpoints": endpoints,
                "neighbors": neighbors,
                "findings": findings,
                "counts": {
                    sev: sum(1 for f in findings if f["severity"] == sev)
                    for sev in ("crit", "warn", "info")
                },
                "health": score,
                "grade": health_grade(score),
            }
        )
    return out


def quality_summary(topo: Topology, runs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Topology-wide KPIs: inventory size, port posture, health, scenario outcomes."""
    inv = device_inventory(topo)
    rep = validate(topo)
    ports = [p for d in inv for p in d["ports"]]
    findings = [f for d in inv for f in d["findings"]]

    # latest run per scenario drives the scenario pass-rate
    latest: dict[str, dict[str, Any]] = {}
    for r in runs or []:
        latest.setdefault(r.get("scenario") or "?", r)
    passes = sum((r.get("counts") or {}).get("pass", 0) for r in latest.values())
    total_steps = sum(sum((r.get("counts") or {}).values()) for r in latest.values())

    health = round(sum(d["health"] for d in inv) / len(inv)) if inv else 100
    return {
        "topology": topo.name,
        "devices": len(inv),
        "by_role": {role: sum(1 for d in inv if d["role"] == role)
                    for role in sorted({d["role"] for d in inv})},
        "endpoints": len(topo.endpoints),
        "ssids": len(topo.ssids),
        "links": build_graph(topo).number_of_edges(),
        "ports": {
            "total": len(ports),
            "nac": sum(1 for p in ports if p["purpose"] == "nac"),
            "ap": sum(1 for p in ports if p["purpose"] == "ap"),
            "uplink": sum(1 for p in ports if p["purpose"] == "uplink"),
            "compliant": sum(1 for p in ports if p["verdict"] == "pass"),
        },
        "findings": {sev: sum(1 for f in findings if f["severity"] == sev)
                     for sev in ("crit", "warn", "info")},
        "health": health,
        "grade": health_grade(health),
        "validation": {"errors": len(rep.errors), "warnings": len(rep.warnings)},
        "scenarios": {
            "ran": len(latest),
            "pass_rate": round(100 * passes / total_steps) if total_steps else None,
            "drift": sum(1 for r in latest.values()
                         if r.get("comparison_status") not in (None, "match", "no-baseline")),
        },
        "worst": sorted(
            ({"name": d["name"], "role": d["role"], "health": d["health"]} for d in inv),
            key=lambda d: d["health"],
        )[:5],
    }
