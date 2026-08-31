# Architecture

```
                    topologies/*.yaml  (intent)
                             │
                    ┌────────▼────────┐
                    │  topology model │  pydantic + networkx
                    │  + validation   │  → mermaid / graph.json
                    └────────┬────────┘
                             │
        ┌────────────────────▼─────────────────────┐
        │              scenario engine             │
        │  steps() → StepResult stream             │
        │  nac_eval: local policy evaluation       │
        └───────┬───────────────────────┬──────────┘
                │                       │
   ┌──────────▼──────┐  ┌───────▼──────────┐  ┌──────▼───────────┐
   │ CatalystCenter  │  │  ISE connector   │  │  WLC connector   │
   │ connector       │  │  (ciscoisesdk)   │  │  (RESTCONF /     │
   │ (dnacentersdk)  │  │                  │  │   requests)      │
   └──────────┬──────┘  └───────┬──────────┘  └──────┬───────────┘
              │      vcrpy cassette (record/replay)  │
        live ─┤                                      ├─ live (opt-in)
              ▼                 ▼                     ▼
   sandboxdnac.cisco.com  devnetsandboxise.cisco.com   Catalyst 9800
      (DevNet always-on)     (DevNet always-on)      (DevNet *reserved*)
              │                 │                     │
              └────────┬────────┴─────────────────────┘
                       ▼
                 ScenarioResult  ──►  expect/compare (deepdiff)  ──►  expected/*.json
                           │
                 runs/<id>/{result,comparison}.json + report.html
                           │
                 CLI (typer/rich)   +   web dashboard (FastAPI + SSE + vis-network)
```

## Why this shape

* **Controllers are too big to virtualize.** ISE and Catalyst Center each need
  16–64 GB RAM. Instead of emulating them, we call the **real** ones that Cisco
  DevNet hosts for free, then cache the answers.

* **`custom_caller`, not the typed SDK methods.** Both SDKs expose
  `api.custom_caller.call_api("GET", path, ...)`. Using it keeps cassettes stable
  across SDK/controller versions and keeps the connector surface tiny.

* **The WLC connector is opt-in.** A Catalyst 9800 is not part of the always-on
  DevNet estate, so `netsimlab/connectors/wlc.py` (plain `requests` over
  RESTCONF, `Cisco-IOS-XE-wireless-*` YANG) only activates when
  `settings.wlc.enabled` is set. When on, it is the preferred RF source for the
  `wireless_rf_exploration` scenario (per-radio channel utilisation, noise,
  interference, air-quality from `rrm-oper` / `radio-oper`) and adds a
  guest-WLAN existence/enable check to `guest_wireless_onboarding`; when off,
  those scenarios are byte-for-byte unchanged and keep using Catalyst Center
  Assurance / the synthetic RF model. Record a `fixtures/wlc/` cassette during a
  sandbox reservation, replay it forever after.

* **vcrpy at the `requests` layer.** One `use_cassette()` context around the SDK
  calls records/replays every HTTP exchange. A custom matcher ignores volatile
  query keys (`timestamp`, …) so replay stays deterministic. `before_record_*`
  hooks scrub `Authorization`, cookies, CSRF tokens and bearer-token response
  bodies before anything is written to disk.

* **Local policy evaluation (`nac_eval.py`).** Auth decisions are resolved by
  evaluating the topology's declared policies against synthetic endpoint
  attributes — no RADIUS server, no test client. The *real* ISE objects
  (authz profiles, dACLs, SGTs, portals) are still fetched from the sandbox to
  prove connectivity and shape.

* **Golden snapshots = "expected real-world output".** `netsim snapshot save`
  stores a full ScenarioResult captured from the live sandbox. Later runs
  `deepdiff` against it with ignore rules for UUIDs / timestamps / health scores,
  and report `match` / `verdict-drift` / `data-drift`.

## Resource budget

| component | RSS |
|---|---|
| `netsim scenario run` (replay) | ~120 MB |
| `netsim serve` dashboard | ~200 MB |
| test suite | ~150 MB |

No Docker, no hypervisor, no GPU. Internet is only used in `record` / `live`.
