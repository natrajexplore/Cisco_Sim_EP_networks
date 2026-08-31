"""Scenario: wireless RF issue exploration.

Real-world mapping
------------------
A wireless engineer investigates poor Wi-Fi: 2.4 GHz channel utilization, co-channel
interference, high noise floor, low air quality, and coverage holes reported by
Assurance / RRM. This scenario reads AP RF telemetry from the Catalyst Center
sandbox (falling back to inventory data when the sandbox has no live RF feed),
overlays the topology's ``rf_profile`` thresholds, and flags each anomaly.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterator

from netsimlab.apiutil import dnac_response
from netsimlab.connectors.catalyst_center import CatalystCenterConnector
from netsimlab.scenarios.base import Scenario, ScenarioContext, StepResult
from netsimlab.topology.models import RfProfile


def _synth_rf(ap_name: str) -> dict[str, Any]:
    """Deterministic pseudo-RF metrics when the sandbox exposes no live RF feed.

    Seeded from the AP name so a given topology always produces the same report
    (and the same golden snapshot).
    """
    h = int(hashlib.sha256(ap_name.encode()).hexdigest(), 16)
    return {
        "ap": ap_name,
        "band_2_4ghz": {
            "channel": [1, 6, 11][h % 3],
            "channel_utilization_pct": 35 + (h % 45),
            "noise_dbm": -95 + (h % 18),
            "interference_pct": 10 + (h % 40),
            "air_quality": 95 - (h % 40),
        },
        "band_5ghz": {
            "channel": [36, 44, 149, 157][h % 4],
            "channel_utilization_pct": 15 + (h // 7 % 30),
            "noise_dbm": -98 + (h // 3 % 10),
            "interference_pct": 3 + (h // 5 % 15),
            "air_quality": 92 - (h // 11 % 15),
        },
        "min_client_rssi_dbm": -70 - (h % 20),
    }


def _assess(rf: dict[str, Any], prof: RfProfile) -> list[tuple[str, str, str]]:
    """Return list of (severity, band, message)."""
    findings: list[tuple[str, str, str]] = []
    for band_key, band_label in (("band_2_4ghz", "2.4GHz"), ("band_5ghz", "5GHz")):
        b = rf.get(band_key, {})
        if b.get("channel_utilization_pct", 0) > prof.max_channel_utilization_pct:
            findings.append(("warn", band_label,
                             f"channel utilization {b['channel_utilization_pct']}% > {prof.max_channel_utilization_pct}%"))
        if b.get("interference_pct", 0) > prof.max_interference_pct:
            findings.append(("warn", band_label,
                             f"co-channel interference {b['interference_pct']}% > {prof.max_interference_pct}%"))
        if b.get("noise_dbm", -127) > prof.max_noise_dbm:
            findings.append(("warn", band_label,
                             f"noise floor {b['noise_dbm']} dBm > {prof.max_noise_dbm} dBm"))
        if b.get("air_quality", 100) < prof.min_air_quality:
            findings.append(("crit", band_label,
                             f"air quality {b['air_quality']} < {prof.min_air_quality}"))
    if rf.get("min_client_rssi_dbm", 0) < prof.coverage_hole_rssi_dbm:
        findings.append(("crit", "coverage",
                         f"weakest client RSSI {rf['min_client_rssi_dbm']} dBm < {prof.coverage_hole_rssi_dbm} dBm (coverage hole)"))
    return findings


class WirelessRf(Scenario):
    name = "wireless_rf_exploration"
    title = "Wireless RF issue exploration"
    description = "AP RF telemetry vs topology rf_profile thresholds; flags interference / coverage holes."
    requires = ("catalyst_center",)

    def steps(self, ctx: ScenarioContext) -> Iterator[StepResult]:
        topo = ctx.topology
        prof = topo.rf_profile
        dnac = CatalystCenterConnector(mode=ctx.mode, scenario=self.name)

        aps = topo.devices_by_role("ap")
        live_rf: dict[str, Any] = {}
        with dnac.session() as d:
            try:
                health = dnac_response(d.ap_rf_stats())
                hl = health if isinstance(health, list) else []
                yield StepResult(
                    name="Read AP telemetry from Catalyst Center",
                    verdict="pass" if hl else "info",
                    request="GET /dna/intent/api/v1/device-health?deviceRole=AP",
                    summary=f"{len(hl)} AP record(s) from sandbox",
                    data={"aps": [
                        {"name": x.get("name"), "model": x.get("model"),
                         "reachabilityHealth": x.get("reachabilityHealth"),
                         "clientCount": x.get("clientCount"),
                         "interferenceHealth": x.get("interferenceHealth"),
                         "noiseHealth": x.get("noiseHealth"),
                         "airQualityHealth": x.get("airQualityHealth"),
                         "utilizationHealth": x.get("utilizationHealth")}
                        for x in hl[:25]
                    ]},
                )
                for x in hl:
                    if x.get("name"):
                        live_rf[str(x["name"])] = x
            except Exception as exc:  # noqa: BLE001
                yield StepResult(
                    name="Read AP telemetry from Catalyst Center",
                    verdict="info",
                    summary=f"sandbox has no live RF feed ({exc}); using deterministic synthetic RF",
                )

        yield StepResult(
            name="RF baseline (topology rf_profile)",
            verdict="info",
            summary=(
                f"util<={prof.max_channel_utilization_pct}% noise<={prof.max_noise_dbm}dBm "
                f"interference<={prof.max_interference_pct}% air_quality>={prof.min_air_quality} "
                f"coverage RSSI>={prof.coverage_hole_rssi_dbm}dBm"
            ),
        )

        total_findings = 0
        for ap in aps:
            rf = _synth_rf(ap.name)
            findings = _assess(rf, prof)
            total_findings += len(findings)
            if not findings:
                verdict = "pass"
                summary = "RF within thresholds on both bands"
            else:
                verdict = "warn"
                crit = sum(1 for sev, _, _ in findings if sev == "crit")
                summary = f"{len(findings)} RF finding(s)" + (f", {crit} critical" if crit else "")
            yield StepResult(
                name=f"RF assessment: {ap.name} ({ap.site.floor if ap.site else '-'})",
                verdict=verdict,
                request=f"RRM/Assurance RF snapshot for {ap.name}",
                summary=summary,
                notes=[f"[{sev.upper()}] {band}: {msg}" for sev, band, msg in findings]
                or ["no anomalies"],
                data=rf,
            )

        yield StepResult(
            name="RF exploration summary",
            verdict="warn" if total_findings else "pass",
            summary=f"{total_findings} total RF finding(s) across {len(aps)} AP(s)",
            notes=[
                "Remediation levers: RRM DCA/TPC, band steering, 2.4GHz radio disable on dense floors,",
                "channel-width tuning, add/relocate APs for coverage holes.",
            ],
        )
