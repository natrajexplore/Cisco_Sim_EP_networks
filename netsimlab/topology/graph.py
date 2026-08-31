"""Build a networkx graph from a topology and run structural validation."""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from netsimlab.topology.models import Topology


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def build_graph(topo: Topology) -> nx.Graph:
    g = nx.Graph()
    for d in topo.devices:
        g.add_node(
            d.name,
            kind="device",
            role=d.role,
            platform=d.platform,
            site=d.site.path() if d.site else None,
        )
    for s in topo.ssids:
        g.add_node(s.name, kind="ssid", security=s.security, auth_method=s.auth_method)
    for e in topo.endpoints:
        g.add_node(e.name, kind="endpoint", mac=e.mac, device_type=e.kind)

    for link in topo.links:
        g.add_edge(link.a, link.b, kind=link.kind, access_vlan=link.access_vlan)
    for ap in topo.devices_by_role("ap"):
        if ap.wlc:
            g.add_edge(ap.name, ap.wlc, kind="capwap")
    for e in topo.endpoints:
        g.add_edge(e.name, e.connects_to, kind="endpoint", port=e.port)

    # keep the graph coherent: SSIDs ride the WLC(s); controllers hang off the
    # first core/distribution device.
    wlcs = [d.name for d in topo.devices_by_role("wlc")]
    for s in topo.ssids:
        for w in wlcs:
            g.add_edge(s.name, w, kind="broadcast")
    upstream = topo.devices_by_role("core") or topo.devices_by_role("distribution")
    if upstream:
        for d in topo.devices_by_role("ise") + topo.devices_by_role("catalyst_center"):
            g.add_edge(d.name, upstream[0].name, kind="mgmt")
    return g


def validate(topo: Topology) -> ValidationReport:
    r = ValidationReport()
    names = {d.name for d in topo.devices}
    ssid_names = {s.name for s in topo.ssids}
    policy_names = {p.name for p in topo.policies}

    if not topo.devices_by_role("catalyst_center"):
        r.warnings.append("no 'catalyst_center' device - catalyst_provisioning scenario will be skipped")
    if not topo.devices_by_role("ise"):
        r.warnings.append("no 'ise' device - NAC scenarios will rely on sandbox defaults only")

    for ap in topo.devices_by_role("ap"):
        if not ap.wlc:
            r.errors.append(f"AP {ap.name!r} has no 'wlc'")
        elif ap.wlc not in names:
            r.errors.append(f"AP {ap.name!r} references unknown wlc {ap.wlc!r}")

    for link in topo.links:
        for end in (link.a, link.b):
            if end not in names and end not in ssid_names:
                r.errors.append(f"link references unknown node {end!r}")

    for s in topo.ssids:
        if s.policy and s.policy not in policy_names:
            r.errors.append(f"SSID {s.name!r} references unknown policy {s.policy!r}")
        if s.auth_method == "guest" and not s.portal:
            r.warnings.append(f"guest SSID {s.name!r} has no 'portal' set")

    for e in topo.endpoints:
        target = e.connects_to
        if target not in names and target not in ssid_names:
            r.errors.append(f"endpoint {e.name!r} connects_to unknown {target!r}")
        if target in names:
            dev = topo.device(target)
            if dev and dev.role not in {"access", "distribution", "core"}:
                r.warnings.append(
                    f"endpoint {e.name!r} connects to {target!r} which is role {dev.role!r}"
                )
        if e.auth_method in {"dot1x"} and not e.identity:
            r.warnings.append(f"endpoint {e.name!r} uses dot1x but has no 'identity'")

    g = build_graph(topo)
    if g.number_of_nodes() and not nx.is_connected(g):
        comps = [sorted(c) for c in nx.connected_components(g)]
        r.warnings.append(f"topology graph is not fully connected: {len(comps)} components")
    return r
