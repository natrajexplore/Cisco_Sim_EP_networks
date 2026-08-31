"""Compare a scenario run to a golden snapshot captured from the real sandbox."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from deepdiff import DeepDiff

from netsimlab.config import EXPECTED_DIR

# Volatile fields that legitimately change between sandbox runs.
IGNORE_REGEX = [
    r"root\['steps'\]\[\d+\]\['data'\]\['network_health'\]",
    r"root\['steps'\]\[\d+\]\['data'\]\['client_health'\]",
    r"root\['started'\]",
    r"root\['ended'\]",
    r".*\['timestamp'\].*",
    r".*\['instanceUuid'\].*",
    r".*\['id'\].*",
    r".*\['lastUpdated'\].*",
    r".*\['collectionStatus'\].*",
    r".*\['upTime'\].*",
    r".*\['bootDateTime'\].*",
]


def snapshot_path(scenario: str) -> Path:
    return EXPECTED_DIR / f"{scenario}.json"


def load_expected(scenario: str) -> dict[str, Any] | None:
    p = snapshot_path(scenario)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_expected(scenario: str, result: dict[str, Any]) -> Path:
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    p = snapshot_path(scenario)
    p.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return p


def _verdict_map(result: dict[str, Any]) -> dict[str, str]:
    return {s["name"]: s["verdict"] for s in result.get("steps", [])}


def compare(scenario: str, result: dict[str, Any]) -> dict[str, Any]:
    """Return {status, summary, verdict_diff, deepdiff}."""
    expected = load_expected(scenario)
    if expected is None:
        return {
            "status": "no-baseline",
            "summary": "no golden snapshot yet - run once with --mode record (needs internet) "
            "then `netsim snapshot save`",
            "verdict_diff": {},
            "deepdiff": {},
        }

    exp_v, got_v = _verdict_map(expected), _verdict_map(result)
    vdiff = {
        name: {"expected": exp_v[name], "actual": got_v.get(name, "MISSING")}
        for name in exp_v
        if got_v.get(name) != exp_v[name]
    }
    for name in got_v:
        if name not in exp_v:
            vdiff[name] = {"expected": "MISSING", "actual": got_v[name]}

    dd = DeepDiff(
        expected,
        result,
        ignore_order=True,
        exclude_regex_paths=IGNORE_REGEX,
        verbose_level=0,
    )
    status = "match" if not vdiff and not dd else ("verdict-drift" if vdiff else "data-drift")
    return {
        "status": status,
        "summary": {
            "verdict_changes": len(vdiff),
            "data_changes": sum(len(v) for v in dd.to_dict().values()) if dd else 0,
        },
        "verdict_diff": vdiff,
        "deepdiff": json.loads(dd.to_json()) if dd else {},
    }
