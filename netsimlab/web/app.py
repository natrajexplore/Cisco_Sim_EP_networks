"""FastAPI dashboard: topology graph, scenario runner (SSE), run history."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from netsimlab.config import Mode, get_settings
from netsimlab.expect import compare as expect_compare
from netsimlab.runner import iter_run, latest_runs, load_run
from netsimlab.scenarios.base import ScenarioResult
from netsimlab.scenarios.registry import list_scenarios
from netsimlab.topology.diagram import to_graph_json, to_mermaid
from netsimlab.topology.graph import validate
from netsimlab.topology.loader import load_topology

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="netsim lab", version="0.1.0")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/api/topology")
def api_topology(file: str | None = None) -> dict[str, Any]:
    path = file or get_settings().topology
    topo = load_topology(path)
    rep = validate(topo)
    return {
        "graph": to_graph_json(topo),
        "mermaid": to_mermaid(topo),
        "validation": {"ok": rep.ok, "errors": rep.errors, "warnings": rep.warnings},
        "path": path,
    }


@app.get("/api/scenarios")
def api_scenarios() -> list[dict[str, Any]]:
    out = []
    for s in list_scenarios():
        exp = expect_compare.load_expected(s.name)
        out.append(
            {
                "name": s.name,
                "title": s.title,
                "description": s.description,
                "requires": list(s.requires),
                "has_snapshot": exp is not None,
                "snapshot_counts": (exp or {}).get("counts"),
            }
        )
    return out


@app.get("/api/runs")
def api_runs(limit: int = 25) -> list[dict[str, Any]]:
    return latest_runs(limit)


@app.get("/api/runs/{run_id}")
def api_run(run_id: str) -> dict[str, Any]:
    try:
        return load_run(run_id)
    except FileNotFoundError:
        raise HTTPException(404, f"run {run_id} not found")


@app.get("/api/settings")
def api_settings() -> dict[str, Any]:
    s = get_settings()
    return {
        "mode": s.mode,
        "topology": s.topology,
        "dnac_base_url": s.dnac.base_url,
        "ise_base_url": s.ise.base_url,
        "wlc_enabled": s.wlc.enabled,
        "wlc_base_url": s.wlc.base_url if s.wlc.enabled else None,
    }


@app.get("/api/scenario/{name}/stream")
async def api_scenario_stream(name: str, mode: str | None = None, topology: str | None = None):
    eff_mode: Mode = (mode or get_settings().mode)  # type: ignore[assignment]
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def worker() -> None:
        final: ScenarioResult | None = None
        try:
            for item in iter_run(name, mode=eff_mode, topology_path=topology):
                if isinstance(item, ScenarioResult):
                    final = item
                    payload = {"type": "result", "data": item.to_dict()}
                else:
                    payload = {"type": "step", "data": item.to_dict()}
                loop.call_soon_threadsafe(queue.put_nowait, payload)
            if final is not None:
                cmp = expect_compare.compare(final.name, final.to_dict())
                loop.call_soon_threadsafe(
                    queue.put_nowait, {"type": "comparison", "data": cmp}
                )
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(
                queue.put_nowait, {"type": "error", "data": {"message": str(exc)}}
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=worker, daemon=True).start()

    async def event_gen():
        while True:
            item = await queue.get()
            if item is None:
                yield {"event": "done", "data": "{}"}
                return
            yield {"event": item["type"], "data": json.dumps(item["data"])}

    return EventSourceResponse(event_gen())


app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
