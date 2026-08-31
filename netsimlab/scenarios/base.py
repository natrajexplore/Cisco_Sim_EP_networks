"""Scenario engine core types."""

from __future__ import annotations

import abc
import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator, Literal

from netsimlab.config import Mode, get_settings
from netsimlab.topology.models import Topology

Verdict = Literal["pass", "fail", "warn", "info"]


@dataclass
class StepResult:
    name: str
    verdict: Verdict = "info"
    summary: str = ""
    request: str = ""
    notes: list[str] = field(default_factory=list)
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # keep payloads small / JSON-safe for the report + SSE
        try:
            json.dumps(d["data"])
        except (TypeError, ValueError):
            d["data"] = _summarize(d["data"])
        return d


def _summarize(obj: Any, limit: int = 20) -> Any:
    if isinstance(obj, list):
        return [_summarize(x) for x in obj[:limit]] + (["..."] if len(obj) > limit else [])
    if isinstance(obj, dict):
        return {k: _summarize(v) for k, v in list(obj.items())[:limit]}
    return str(obj)


@dataclass
class ScenarioResult:
    name: str
    title: str
    mode: Mode
    topology: str
    started: str
    ended: str = ""
    steps: list[StepResult] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        c = {"pass": 0, "fail": 0, "warn": 0, "info": 0}
        for s in self.steps:
            c[s.verdict] += 1
        return c

    @property
    def ok(self) -> bool:
        return self.counts["fail"] == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "mode": self.mode,
            "topology": self.topology,
            "started": self.started,
            "ended": self.ended,
            "counts": self.counts,
            "ok": self.ok,
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class ScenarioContext:
    topology: Topology
    mode: Mode

    @property
    def settings(self):
        return get_settings()


class Scenario(abc.ABC):
    name: str = "scenario"
    title: str = "Scenario"
    description: str = ""
    requires: tuple[str, ...] = ()

    @abc.abstractmethod
    def steps(self, ctx: ScenarioContext) -> Iterator[StepResult]:
        """Yield StepResults in order. May open connector sessions."""

    def run(self, ctx: ScenarioContext) -> Iterator[StepResult]:
        yield from self.steps(ctx)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
