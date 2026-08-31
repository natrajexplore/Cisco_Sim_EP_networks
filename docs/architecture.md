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
       ┌────────▼────────┐     ┌────────▼─────────┐
       │ CatalystCenter  │     │  ISE connector   │
       │ connector       │     │  (ciscoisesdk)   │
       │ (dnacentersdk)  │     │                  │
       └────────┬────────┘     └────────┬─────────┘
                │      vcrpy cassette    │
        live ───┤      (record/replay)   ├─── live
                ▼                        ▼
     sandboxdnac.cisco.com     devnetsandboxise.cisco.com
        (DevNet always-on)        (DevNet always-on)
                │                        │
                └──────────┬─────────────┘
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
