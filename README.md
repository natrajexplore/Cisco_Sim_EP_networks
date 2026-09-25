# netsim lab

![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)
![tests](https://img.shields.io/badge/tests-33%20passing-brightgreen)
![scenarios](https://img.shields.io/badge/scenarios-6-2a9d8f)
![mode](https://img.shields.io/badge/offline-replay%20%7C%20record%20%7C%20live-informational)
![Cisco DevNet](https://img.shields.io/badge/Cisco%20DevNet-always--on%20sandboxes-1BA0D7?logo=cisco&logoColor=white)

A **lightweight** framework for exploring enterprise 3D view network architecture and
simulating real-world **Cisco ISE / NAC, wireless and Catalyst Center** scenarios
— without Cisco Modeling Labs, without controller VMs, on a laptop with **8 GB RAM**.

It drives the **free Cisco DevNet always-on sandboxes** (real Catalyst Center, real
ISE — no VPN, no reservation) over the internet, **records every response**, and
**replays them offline** so the same scenarios run deterministically with no
connectivity and near-zero resource use.

```
CLI ~120 MB RAM   ·   dashboard ~200 MB   ·   no Docker   ·   no GPU
```

## What it does

| Scenario | Real-world mapping | Talks to |
|---|---|---|
| `wired_dot1x_mab` | Employee 802.1X + printer MAB: policy sets, authz profiles, dACLs, VLAN, SGT | ISE |
| `access_port_nac_validation` | Switchport config for NAC: host-mode, 802.1X/MAB, closed/open, CoA, dACL, periodic re-auth; AP ports: PoE, trunk, QoS trust | topology intent (+ Catalyst Center config cross-check) |
| `guest_wireless_onboarding` | Self-registered guest portal → CoA → internet-only access | ISE + Catalyst Center |
| `endpoint_profiling_posture` | Device profiling (device sensor) + posture compliance / quarantine | ISE |
| `catalyst_provisioning_assurance` | Site hierarchy, inventory, SWIM, network/client health, issues | Catalyst Center |
| `wireless_rf_exploration` | AP RF telemetry vs thresholds: interference, noise, air quality, coverage holes | Catalyst Center *(or Catalyst 9800 WLC)* |

Each run is compared to a **golden "expected output" snapshot** captured from the
real sandbox, so you see exactly where live behaviour drifts from the baseline.

## Optional: Catalyst 9800 WLC source

The wireless scenarios can pull real per-radio RF and WLAN state straight off a
**Catalyst 9800** over RESTCONF. It is off by default (no always-on 9800 sandbox
exists). Reserve the *Catalyst 9800 Wireless* DevNet sandbox, connect the VPN,
then:

```bash
export NETSIM_WLC_ENABLED=true
export NETSIM_WLC_BASE_URL=https://<wlc-mgmt-ip>
export NETSIM_WLC_USERNAME=... NETSIM_WLC_PASSWORD=...
netsim sandbox                                     # WLC row appears
netsim scenario run wireless_rf_exploration --mode record   # captures fixtures/wlc/
```

With it enabled, `wireless_rf_exploration` uses the 9800's `rrm-oper` /
`radio-oper` data (channel utilisation, noise, interference, air quality) instead
of the synthetic model, and `guest_wireless_onboarding` gains a guest-WLAN
existence/enable check. Disabled, both scenarios are unchanged.

## Install

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt      # Windows
venv\Scripts\pip install -e .
cp .env.example .env                               # optional: adjust sandbox creds
```

## Use

```bash
netsim topology validate                          # check the topology model
netsim topology diagram -f mermaid                # render the topology
netsim sandbox                                    # check DevNet sandbox reachability

netsim scenario list
netsim scenario run wired_dot1x_mab               # replay (offline, default)
netsim scenario run catalyst_provisioning_assurance --mode record   # hit the live sandbox + save cassette
netsim snapshot save wired_dot1x_mab --mode replay                  # (re)bless the golden snapshot

netsim runs                                       # run history
netsim report <run-id>                            # regenerate the HTML report

netsim serve                                      # dashboard at http://127.0.0.1:8080
```

### Modes

| mode | network | use |
|---|---|---|
| `replay` *(default)* | none | offline, deterministic, CI |
| `record` | live | capture fresh cassettes + snapshots from the sandbox |
| `live` | live | no recording, always current |

## Topology

Topologies are plain YAML (`topologies/campus-small.yaml`) — sites, devices,
SSIDs, endpoints, the **intended** NAC / RF policy, and `access_ports:` (the
intended switchport config; NAC ports are auto-derived from endpoints, AP/uplink
ports from links with `a_port` / `b_port` names). `netsim topology validate`
checks structural integrity; scenarios compare the sandbox against this intent.

The dashboard topology graph is interactive — hover (or click) a device, link or
endpoint to see its connected port IDs, the neighbor on the other end and that
neighbor's port, plus link kind / VLAN / auth method.

## Layout

```
netsimlab/
  topology/      models + loader + graph validation + mermaid/json export
  connectors/    dnacentersdk / ciscoisesdk / Catalyst 9800 RESTCONF wrappers
                 with record/replay (vcrpy)
  scenarios/     the 6 scenarios + registry
  nac_eval.py    local policy evaluator (no RADIUS server needed)
  port_eval.py   local switchport (NAC / AP / uplink) config checker
  expect/        deepdiff comparison to golden snapshots
  runner.py      execute + persist + compare
  report/        HTML report
  web/           FastAPI dashboard + SPA (topology graph, SSE runner, history)
fixtures/        vcrpy cassettes (committed, secrets scrubbed)
expected/        golden snapshots (committed)
```

See [`docs/architecture.md`](docs/architecture.md) and
[`docs/references.md`](docs/references.md) (DevNet sandboxes / SDKs / repos used).

## Not in v1

No packet-level emulation (no containerlab / CML). The connector and scenario
layers leave hooks for a future opt-in `--mode emulate` that adds an FRR / Cisco
IOL access layer doing real 802.1X.
