"""Render a topology as a Mermaid diagram (docs) and as graph JSON (dashboard)."""

from __future__ import annotations

from typing import Any

from netsimlab.topology.graph import build_graph
from netsimlab.topology.models import Topology

_ROLE_SHAPE = {
    "catalyst_center": ("[[", "]]"),
    "ise": ("[[", "]]"),
    "core": ("((", "))"),
    "distribution": ("[", "]"),
    "access": ("[", "]"),
    "border": ("[", "]"),
    "wlc": ("[/", "/]"),
    "ap": ("(", ")"),
    "firewall": ("{{", "}}"),
}


def _safe_id(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name)


def to_mermaid(topo: Topology) -> str:
    lines = ["graph TD"]
    for d in topo.devices:
        lo, hi = _ROLE_SHAPE.get(d.role, ("[", "]"))
        lines.append(f'    {_safe_id(d.name)}{lo}"{d.name}<br/>{d.role}"{hi}')
    for s in topo.ssids:
        lines.append(f'    {_safe_id(s.name)}(["SSID {s.name}<br/>{s.security}"])')
    for e in topo.endpoints:
        lines.append(f'    {_safe_id(e.name)}["{e.name}<br/>{e.kind}"]')

    for link in topo.links:
        lines.append(f"    {_safe_id(link.a)} --- {_safe_id(link.b)}")
    for ap in topo.devices_by_role("ap"):
        if ap.wlc:
            lines.append(f"    {_safe_id(ap.name)} -.CAPWAP.- {_safe_id(ap.wlc)}")
    for e in topo.endpoints:
        label = e.auth_method
        lines.append(f"    {_safe_id(e.name)} -- {label} --> {_safe_id(e.connects_to)}")
    return "\n".join(lines)


def to_graph_json(topo: Topology) -> dict[str, Any]:
    g = build_graph(topo)
    nodes = [{"id": n, **{k: v for k, v in data.items() if v is not None}} for n, data in g.nodes(data=True)]
    edges = [
        {"from": a, "to": b, **{k: v for k, v in data.items() if v is not None}}
        for a, b, data in g.edges(data=True)
    ]
    return {"name": topo.name, "description": topo.description, "nodes": nodes, "edges": edges}
