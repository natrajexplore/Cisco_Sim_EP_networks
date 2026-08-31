"""Scenario: endpoint profiling + posture.

Real-world mapping
------------------
ISE profiles endpoints from CDP/LLDP/DHCP/RADIUS attributes (device sensor) and
assigns them to logical profiles / endpoint identity groups. Posture then checks
employee machines for compliance and quarantines the non-compliant ones. This
scenario pulls the real ISE endpoint identity groups + endpoints from the DevNet
sandbox, then resolves the topology's profiler and posture intent per endpoint.
"""

from __future__ import annotations

from typing import Iterator

from netsimlab import nac_eval
from netsimlab.apiutil import ise_resources, names
from netsimlab.connectors.ise import IseConnector
from netsimlab.scenarios.base import Scenario, ScenarioContext, StepResult


class ProfilingPosture(Scenario):
    name = "endpoint_profiling_posture"
    title = "Endpoint profiling + posture"
    description = "ISE profiler + posture compliance / quarantine."
    requires = ("ise",)

    def steps(self, ctx: ScenarioContext) -> Iterator[StepResult]:
        topo = ctx.topology
        ise = IseConnector(mode=ctx.mode, scenario=self.name)

        with ise.session() as sess:
            epgroups = ise_resources(sess.endpoint_groups())
            yield StepResult(
                name="Fetch endpoint identity groups (profiler targets)",
                verdict="pass" if epgroups else "warn",
                request="GET /ers/config/endpointgroup",
                summary=f"{len(epgroups)} endpoint group(s)",
                data={"endpoint_groups": names(epgroups)},
            )
            eps = ise_resources(sess.endpoints())
            yield StepResult(
                name="Fetch known endpoints from ISE",
                verdict="pass" if eps else "warn",
                request="GET /ers/config/endpoint",
                summary=f"{len(eps)} endpoint(s) already learned by ISE",
                data={"sample": [e.get("mac") or e.get("name") for e in eps[:10]]},
            )

        # profiling
        for ep in topo.endpoints:
            if not ep.attributes:
                continue
            dec = nac_eval.evaluate(topo, ep, kind="profiler")
            hit = dec.matched_policy is not None
            yield StepResult(
                name=f"Profile {ep.name} (mac {ep.mac})",
                verdict="pass" if hit else "info",
                request=f"device-sensor attrs: {', '.join(f'{k}={v}' for k, v in ep.attributes.items())}",
                summary=(
                    f"logical profile: {dec.profile or '(unclassified -> Unknown)'}"
                    + (f", SGT {dec.sgt}" if dec.sgt else "")
                ),
                notes=dec.reasons,
                data=dec.as_dict(),
            )

        # posture
        posture_targets = [e for e in topo.endpoints if "posture_status" in e.attributes]
        if not posture_targets:
            yield StepResult(name="Posture assessment", verdict="info",
                             summary="no endpoints carry a posture_status attribute")
        for ep in posture_targets:
            dec = nac_eval.evaluate(topo, ep, kind="posture")
            status = ep.attributes.get("posture_status")
            compliant = status == "compliant"
            yield StepResult(
                name=f"Posture assessment: {ep.name}",
                verdict="pass" if compliant else "warn",
                request=f"posture report: status={status}",
                summary=(
                    f"{dec.matched_policy} -> vlan={dec.vlan} sgt={dec.sgt} dacl={dec.dacl}"
                ),
                notes=(
                    ["compliant - full access"]
                    if compliant
                    else ["non-compliant - CoA to quarantine / remediation VLAN"]
                )
                + dec.reasons,
                data=dec.as_dict(),
            )
