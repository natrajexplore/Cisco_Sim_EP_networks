# Scenarios

Run any of these with `netsim scenario run <name> [--mode replay|record|live]`.
Every scenario yields an ordered list of steps, each with a verdict
(`pass` / `fail` / `warn` / `info`) and the request it made.

---

## `wired_dot1x_mab` — Wired 802.1X + MAB NAC

**Story.** An employee laptop (802.1X, cert/identity) and a floor printer (MAB, no
supplicant) plug into a Catalyst 9300. ISE authenticates each, assigns a VLAN +
TrustSec SGT and pushes a downloadable ACL.

**Steps.** Fetches the real ISE building blocks — NADs, authorization profiles,
dACLs, SGTs, identity groups — then simulates a RADIUS Access-Request per wired
endpoint and resolves the topology's `authz` policies. Checks
`expected_vlan` / `expected_sgt` / `expected_authz_profile`.

**Expected output.** 8 pass — 5 ISE fetches + 3 endpoint authorizations
(employee → VLAN 20/Employees, printer → VLAN 30/Printers/PRINT_ONLY,
IP phone → VLAN 40/Voice).

---

## `guest_wireless_onboarding` — Guest wireless onboarding

**Story.** A visitor joins the open `GUEST` SSID, hits the ISE self-registered
guest portal, registers, and after a CoA re-auth gets internet-only access.

**Steps.** Fetches ISE portals / guest types / sponsor portals and the Catalyst
Center wireless profiles, checks the guest SSID design, then walks each guest
endpoint through **pre-auth** (URL-redirect to portal) and **post-auth**
(CoA → Guest-Permit, VLAN 50 / Guests / GUEST_INTERNET).

---

## `endpoint_profiling_posture` — Profiling + posture

**Story.** ISE profiles endpoints from CDP/LLDP/DHCP/RADIUS attributes and sorts
them into logical profiles; posture then checks employee machines and quarantines
the non-compliant.

**Steps.** Fetches ISE endpoint identity groups + learned endpoints, resolves the
`profiler` policies for attribute-bearing endpoints (e.g. IP phone → IP-Phones /
Voice SGT), then runs `posture` policies — compliant → full access, non-compliant
→ quarantine VLAN 999 / REMEDIATION_ONLY (a `warn`).

---

## `catalyst_provisioning_assurance` — Catalyst Center

**Story.** An operator builds the site hierarchy, discovers devices, manages
golden images (SWIM) and watches Assurance.

**Steps.** Reads `/site`, `/network-device`, `/image/importation`,
`/network-health`, `/client-health`, `/issues` from the live sandbox; cross-checks
the topology's declared platforms against the sandbox inventory; flags P1 issues.

---

## `wireless_rf_exploration` — RF issues

**Story.** A wireless engineer investigates poor Wi-Fi: 2.4 GHz utilization,
co-channel interference, noise floor, air quality, coverage holes.

**Steps.** Pulls AP telemetry from Catalyst Center (or falls back to a
deterministic synthetic RF model), overlays the topology's `rf_profile`
thresholds, and reports per-AP findings + remediation levers (RRM DCA/TPC, band
steering, 2.4 GHz radio disable, added APs).
