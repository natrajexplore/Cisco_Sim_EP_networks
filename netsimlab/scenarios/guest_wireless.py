"""Scenario: guest wireless onboarding.

Real-world mapping
------------------
A visitor joins the open ``GUEST`` SSID, is redirected to the ISE self-registered
guest portal, registers, and after authentication is granted internet-only access
via CoA. This scenario pulls the real ISE guest portals / guest types / sponsor
portals and the Catalyst Center wireless design, then walks the portal state
machine and checks the pre-auth redirect and post-auth permit decisions.
"""

from __future__ import annotations

from typing import Iterator

from netsimlab import nac_eval
from netsimlab.apiutil import dnac_response, ise_resources, names
from netsimlab.connectors.catalyst_center import CatalystCenterConnector
from netsimlab.connectors.ise import IseConnector
from netsimlab.scenarios.base import Scenario, ScenarioContext, StepResult


class GuestWireless(Scenario):
    name = "guest_wireless_onboarding"
    title = "Guest wireless onboarding"
    description = "ISE self-registered guest portal + CoA + Catalyst Center SSID."
    requires = ("ise", "catalyst_center")

    def steps(self, ctx: ScenarioContext) -> Iterator[StepResult]:
        topo = ctx.topology
        ise = IseConnector(mode=ctx.mode, scenario=self.name)
        dnac = CatalystCenterConnector(mode=ctx.mode, scenario=self.name)

        with ise.session() as sess:
            portals = ise_resources(sess.portals())
            yield StepResult(
                name="Fetch ISE portals",
                verdict="pass" if portals else "warn",
                request="GET /ers/config/portal",
                summary=f"{len(portals)} portal(s)",
                data={"portals": names(portals)},
            )
            gtypes = ise_resources(sess.guest_types())
            yield StepResult(
                name="Fetch guest types",
                verdict="pass" if gtypes else "warn",
                request="GET /ers/config/guesttype",
                summary=f"{len(gtypes)} guest type(s)",
                data={"guest_types": names(gtypes)},
            )
            sponsors = ise_resources(sess.sponsor_portals())
            yield StepResult(
                name="Fetch sponsor portals",
                verdict="pass" if sponsors else "warn",
                request="GET /ers/config/sponsorportal",
                summary=f"{len(sponsors)} sponsor portal(s)",
                data={"sponsor_portals": names(sponsors)},
            )

        try:
            with dnac.session() as d:
                profiles = dnac_response(d.wireless_ssids())
                yield StepResult(
                    name="Fetch Catalyst Center wireless profiles",
                    verdict="pass",
                    request="GET /dna/intent/api/v1/wireless/profile",
                    summary=f"{len(profiles) if isinstance(profiles, list) else 0} wireless profile(s)",
                    data={"wireless_profiles": profiles if isinstance(profiles, list) else profiles},
                )
        except Exception as exc:  # noqa: BLE001
            yield StepResult(
                name="Fetch Catalyst Center wireless profiles",
                verdict="warn",
                summary=f"wireless design not available on sandbox: {exc}",
            )

        guest_ssid = next((s for s in topo.ssids if s.auth_method == "guest"), None)
        if guest_ssid is None:
            yield StepResult(name="Guest SSID present in topology", verdict="fail",
                             summary="no guest SSID defined")
            return
        yield StepResult(
            name=f"Guest SSID '{guest_ssid.name}' design check",
            verdict="pass" if guest_ssid.portal else "warn",
            summary=f"security={guest_ssid.security} portal={guest_ssid.portal!r} vlan={guest_ssid.vlan}",
        )

        guests = [e for e in topo.endpoints if e.auth_method == "guest"]
        for ep in guests:
            ep_pre = ep.model_copy(deep=True)
            ep_pre.attributes = {**ep.attributes, "portal_state": "pre-auth"}
            dec_pre = nac_eval.evaluate(topo, ep_pre, kind="authz")
            yield StepResult(
                name=f"{ep.name}: associate to '{guest_ssid.name}' (pre-auth)",
                verdict="pass" if dec_pre.url_redirect else "fail",
                request=f"MAB mac={ep.mac} -> portal redirect",
                summary=f"{dec_pre.matched_policy} -> url_redirect={dec_pre.url_redirect} vlan={dec_pre.vlan}",
                notes=dec_pre.reasons,
                data=dec_pre.as_dict(),
            )

            ep_post = ep.model_copy(deep=True)
            ep_post.attributes = {**ep.attributes, "portal_state": "authenticated"}
            dec_post = nac_eval.evaluate(topo, ep_post, kind="authz")
            verdict, notes = nac_eval.check_expectations(ep, dec_post)
            yield StepResult(
                name=f"{ep.name}: portal registration complete -> CoA re-auth",
                verdict=verdict,
                request="CoA (Reauth) issued by ISE",
                summary=f"{dec_post.matched_policy} -> vlan={dec_post.vlan} sgt={dec_post.sgt} dacl={dec_post.dacl}",
                notes=notes + dec_post.reasons,
                data=dec_post.as_dict(),
            )
