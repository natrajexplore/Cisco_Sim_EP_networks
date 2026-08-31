# netsim lab

A **lightweight** framework for exploring enterprise network architecture and
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
| `guest_wireless_onboarding` | Self-registered guest portal → CoA → internet-only access | ISE + Catalyst Center |
| `endpoint_profiling_posture` | Device profiling (device sensor) + posture compliance / quarantine | ISE |
| `catalyst_provisioning_assurance` | Site hierarchy, inventory, SWIM, network/client health, issues | Catalyst Center |
| `wireless_rf_exploration` | AP RF telemetry vs thresholds: interference, noise, air quality, coverage holes | Catalyst Center |

Each run is compared to a **golden "expected output" snapshot** captured from the
real sandbox, so you see exactly where live behaviour drifts from the baseline.

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
SSIDs, endpoints and the **intended** NAC / RF policy. `netsim topology validate`
checks structural integrity; scenarios compare the sandbox against this intent.

## Layout

```
netsimlab/
  topology/      models + loader + graph validation + mermaid/json export
  connectors/    dnacentersdk / ciscoisesdk wrappers with record/replay (vcrpy)
  scenarios/     the 5 scenarios + registry
  nac_eval.py    local policy evaluator (no RADIUS server needed)
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
