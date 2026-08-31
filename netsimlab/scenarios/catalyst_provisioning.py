"""Scenario: Catalyst Center provisioning + assurance.

Real-world mapping
------------------
A network operator builds the site hierarchy, discovers devices, manages golden
software images (SWIM) and watches network / client health and open issues in
Assurance. This scenario reads all of that from the DevNet always-on Catalyst
Center sandbox and checks it against the topology's declared inventory.
"""

from __future__ import annotations

from typing import Iterator

from netsimlab.apiutil import dnac_response, names
from netsimlab.connectors.catalyst_center import CatalystCenterConnector
from netsimlab.scenarios.base import Scenario, ScenarioContext, StepResult


class CatalystProvisioning(Scenario):
    name = "catalyst_provisioning_assurance"
    title = "Catalyst Center provisioning + assurance"
    description = "Site hierarchy, inventory, SWIM, network/client health, issues."
    requires = ("catalyst_center",)

    def steps(self, ctx: ScenarioContext) -> Iterator[StepResult]:
        topo = ctx.topology
        dnac = CatalystCenterConnector(mode=ctx.mode, scenario=self.name)

        with dnac.session() as d:
            sites = dnac_response(d.sites())
            site_names = names(sites) if isinstance(sites, list) else []
            yield StepResult(
                name="Read site hierarchy",
                verdict="pass" if site_names else "warn",
                request="GET /dna/intent/api/v1/site",
                summary=f"{len(site_names)} site(s) in Catalyst Center",
                data={"sites": site_names},
            )

            devices = dnac_response(d.devices())
            dev_list = devices if isinstance(devices, list) else []
            hostnames = sorted(str(x.get("hostname")) for x in dev_list if x.get("hostname"))
            reachable = [x for x in dev_list if str(x.get("reachabilityStatus", "")).lower() == "reachable"]
            yield StepResult(
                name="Read device inventory",
                verdict="pass" if dev_list else "fail",
                request="GET /dna/intent/api/v1/network-device",
                summary=f"{len(dev_list)} device(s), {len(reachable)} reachable",
                data={
                    "devices": [
                        {
                            "hostname": x.get("hostname"),
                            "platformId": x.get("platformId"),
                            "role": x.get("role"),
                            "reachabilityStatus": x.get("reachabilityStatus"),
                            "softwareVersion": x.get("softwareVersion"),
                        }
                        for x in dev_list
                    ]
                },
            )

            # topology intent vs sandbox reality
            want_platforms = {d_.platform for d_ in topo.devices if d_.platform != "unknown"}
            have_platforms = {str(x.get("platformId")) for x in dev_list if x.get("platformId")}
            overlap = sorted(want_platforms & have_platforms)
            yield StepResult(
                name="Topology inventory vs Catalyst Center",
                verdict="info",
                summary=(
                    f"{len(overlap)} platform family match(es) between topology and sandbox"
                ),
                notes=[f"topology platforms: {sorted(want_platforms)}", f"matched: {overlap}"],
                data={"hostnames_in_sandbox": hostnames},
            )

            try:
                images = dnac_response(d.software_images())
                img_list = images if isinstance(images, list) else []
                golden = [i for i in img_list if i.get("isTaggedGolden")]
                yield StepResult(
                    name="SWIM: software image repository",
                    verdict="pass" if img_list else "warn",
                    request="GET /dna/intent/api/v1/image/importation",
                    summary=f"{len(img_list)} image(s), {len(golden)} tagged golden",
                    data={"images": [i.get("name") for i in img_list[:15]]},
                )
            except Exception as exc:  # noqa: BLE001
                yield StepResult(name="SWIM: software image repository", verdict="warn",
                                 summary=f"not available: {exc}")

            try:
                nh = dnac_response(d.network_health())
                overall = None
                if isinstance(nh, list) and nh:
                    overall = nh[0].get("healthScore") or nh[0].get("score")
                yield StepResult(
                    name="Assurance: overall network health",
                    verdict="pass" if overall is not None else "info",
                    request="GET /dna/intent/api/v1/network-health",
                    summary=f"network health score: {overall}",
                    data={"network_health": nh},
                )
            except Exception as exc:  # noqa: BLE001
                yield StepResult(name="Assurance: overall network health", verdict="warn",
                                 summary=f"not available: {exc}")

            try:
                ch = dnac_response(d.client_health())
                yield StepResult(
                    name="Assurance: client health",
                    verdict="info",
                    request="GET /dna/intent/api/v1/client-health",
                    summary="client health scores retrieved",
                    data={"client_health": ch},
                )
            except Exception as exc:  # noqa: BLE001
                yield StepResult(name="Assurance: client health", verdict="warn",
                                 summary=f"not available: {exc}")

            try:
                issues = dnac_response(d.issues())
                issue_list = issues if isinstance(issues, list) else []
                p1 = [i for i in issue_list if str(i.get("priority")) in {"P1", "1"}]
                yield StepResult(
                    name="Assurance: open issues",
                    verdict="warn" if p1 else ("info" if issue_list else "pass"),
                    request="GET /dna/intent/api/v1/issues",
                    summary=f"{len(issue_list)} open issue(s), {len(p1)} P1",
                    data={"issues": [
                        {"name": i.get("name"), "priority": i.get("priority"),
                         "status": i.get("status"), "deviceId": i.get("deviceId")}
                        for i in issue_list[:20]
                    ]},
                )
            except Exception as exc:  # noqa: BLE001
                yield StepResult(name="Assurance: open issues", verdict="warn",
                                 summary=f"not available: {exc}")
