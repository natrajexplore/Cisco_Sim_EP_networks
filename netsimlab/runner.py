"""Run a scenario end to end: execute steps, persist artifacts, compare to golden."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from netsimlab.config import RUNS_DIR, Mode, get_settings
from netsimlab.expect import compare as expect_compare
from netsimlab.scenarios.base import ScenarioContext, ScenarioResult, StepResult, now_iso
from netsimlab.scenarios.registry import get_scenario
from netsimlab.topology.loader import load_topology

StepCallback = Callable[[StepResult], None]


@dataclass
class RunArtifacts:
    run_id: str
    result: ScenarioResult
    comparison: dict[str, Any]
    directory: Path


def _run_id(scenario: str) -> str:
    return f"{now_iso().replace(':', '').replace('-', '')}_{scenario}"


def iter_run(
    scenario_name: str,
    *,
    mode: Mode | None = None,
    topology_path: str | None = None,
) -> Iterator[StepResult | ScenarioResult]:
    """Yield each StepResult as it happens, then a final ScenarioResult."""
    settings = get_settings()
    mode = mode or settings.mode
    topo = load_topology(topology_path or settings.topology)
    scenario = get_scenario(scenario_name)
    ctx = ScenarioContext(topology=topo, mode=mode)

    result = ScenarioResult(
        name=scenario.name,
        title=scenario.title,
        mode=mode,
        topology=topo.name,
        started=now_iso(),
    )
    try:
        for step in scenario.run(ctx):
            result.steps.append(step)
            yield step
    except Exception as exc:  # noqa: BLE001
        err = StepResult(
            name=f"{scenario.title}: aborted",
            verdict="fail",
            summary=f"{type(exc).__name__}: {exc}",
        )
        result.steps.append(err)
        yield err
    result.ended = now_iso()
    yield result


def run(
    scenario_name: str,
    *,
    mode: Mode | None = None,
    topology_path: str | None = None,
    on_step: StepCallback | None = None,
    persist: bool = True,
) -> RunArtifacts:
    result: ScenarioResult | None = None
    for item in iter_run(scenario_name, mode=mode, topology_path=topology_path):
        if isinstance(item, ScenarioResult):
            result = item
        elif on_step is not None:
            on_step(item)
    assert result is not None

    comparison = expect_compare.compare(result.name, result.to_dict())

    run_id = _run_id(result.name)
    directory = RUNS_DIR / run_id
    if persist:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "result.json").write_text(
            json.dumps(result.to_dict(), indent=2), encoding="utf-8"
        )
        (directory / "comparison.json").write_text(
            json.dumps(comparison, indent=2), encoding="utf-8"
        )
    return RunArtifacts(run_id=run_id, result=result, comparison=comparison, directory=directory)


def latest_runs(limit: int = 20) -> list[dict[str, Any]]:
    if not RUNS_DIR.exists():
        return []
    out = []
    for d in sorted(RUNS_DIR.iterdir(), reverse=True):
        rp = d / "result.json"
        if not rp.exists():
            continue
        data = json.loads(rp.read_text(encoding="utf-8"))
        cp = d / "comparison.json"
        comp = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else {}
        out.append(
            {
                "run_id": d.name,
                "scenario": data.get("name"),
                "title": data.get("title"),
                "mode": data.get("mode"),
                "ok": data.get("ok"),
                "counts": data.get("counts"),
                "started": data.get("started"),
                "comparison_status": comp.get("status"),
            }
        )
        if len(out) >= limit:
            break
    return out


def load_run(run_id: str) -> dict[str, Any]:
    d = RUNS_DIR / run_id
    result = json.loads((d / "result.json").read_text(encoding="utf-8"))
    comp_path = d / "comparison.json"
    comparison = json.loads(comp_path.read_text(encoding="utf-8")) if comp_path.exists() else {}
    return {"run_id": run_id, "result": result, "comparison": comparison}
