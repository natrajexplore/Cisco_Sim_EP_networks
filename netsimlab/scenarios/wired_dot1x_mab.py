"""Scenario: wired 802.1X + MAB NAC.

Real-world mapping
------------------
An employee laptop (802.1X) and a floor printer (MAB) plug into a Catalyst 9300
access switch. ISE authenticates them, assigns a VLAN + SGT and pushes a
downloadable ACL. This scenario pulls the *real* ISE policy building blocks from
the DevNet always-on sandbox, then resolves the topology's authorization intent
for every wired endpoint and checks the result.
"""

from __future__ import annotations

from typing import Iterator

from netsimlab import nac_eval
from netsimlab.apiutil import ise_resources, names
from netsimlab.connectors.ise import IseConnector
from netsimlab.scenarios.base import Scenario, ScenarioContext, StepResult


class WiredDot1xMab(Scenario):
    name = "wired_dot1x_mab"
    title = "Wired 802.1X + MAB NAC"
    description = "Employee dot1x + printer MAB against the DevNet ISE sandbox."
    requires = ("ise",)

    def steps(self, ctx: ScenarioContext) -> Iterator[StepResult]:
        topo = ctx.topology
        ise = IseConnector(mode=ctx.mode, scenario=self.name)

        with ise.session() as sess:
            nads = ise_resources(sess.network_devices())
            yield StepResult(
                name="Fetch Network Access Devices (NADs) from ISE",
                verdict="pass" if nads else "warn",
                request="GET /ers/config/networkdevice",
                summary=f"{len(nads)} NAD(s) registered in ISE",
                data={"nads": names(nads)},
            )

            authz = ise_resources(sess.authorization_profiles())
            yield StepResult(
                name="Fetch Authorization Profiles",
                verdict="pass" if authz else "fail",
                request="GET /ers/config/authorizationprofile",
                summary=f"{len(authz)} authorization profiles",
                data={"profiles": names(authz)},
            )

            dacls = ise_resources(sess.downloadable_acls())
            yield StepResult(
                name="Fetch Downloadable ACLs",
                verdict="pass" if dacls else "warn",
                request="GET /ers/config/downloadableacl",
                summary=f"{len(dacls)} dACL(s)",
                data={"dacls": names(dacls)},
            )

            sgts = ise_resources(sess.sgts())
            yield StepResult(
                name="Fetch TrustSec Security Group Tags",
                verdict="pass" if sgts else "warn",
                request="GET /ers/config/sgt",
                summary=f"{len(sgts)} SGT(s)",
                data={"sgts": names(sgts)},
            )

            groups = ise_resources(sess.identity_groups())
            yield StepResult(
                name="Fetch Identity Groups",
                verdict="pass" if groups else "warn",
                request="GET /ers/config/identitygroup",
                summary=f"{len(groups)} identity group(s)",
                data={"identity_groups": names(groups)},
            )

        wired = [e for e in topo.endpoints if e.auth_method in {"dot1x", "mab"} and topo.device(e.connects_to)]
        for ep in wired:
            dec = nac_eval.evaluate(topo, ep, kind="authz")
            verdict, notes = nac_eval.check_expectations(ep, dec)
            yield StepResult(
                name=f"Authorize {ep.name} ({ep.auth_method.upper()}) on {ep.connects_to} {ep.port or ''}".strip(),
                verdict=verdict,
                request=f"simulated RADIUS Access-Request mac={ep.mac} identity={ep.identity or '-'}",
                summary=(
                    f"{dec.matched_policy or 'DENY'} -> vlan={dec.vlan} sgt={dec.sgt} dacl={dec.dacl}"
                ),
                notes=notes + dec.reasons,
                data=dec.as_dict(),
            )
