"""Every scenario must replay offline from its committed cassette and match
its golden snapshot. This is the regression net - it needs no internet.
"""

import pytest

from netsimlab.expect import compare as expect_compare
from netsimlab.runner import run
from netsimlab.scenarios.registry import REGISTRY

SCENARIOS = sorted(REGISTRY)


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario_replays_and_matches_snapshot(name):
    if expect_compare.load_expected(name) is None:
        pytest.skip(f"no golden snapshot for {name} yet (run: netsim snapshot save {name})")
    arts = run(name, mode="replay", persist=False)
    assert arts.result.steps, "scenario produced no steps"
    # no step should be an internal abort
    aborts = [s for s in arts.result.steps if s.name.endswith("aborted")]
    assert not aborts, aborts[0].summary if aborts else ""
    assert arts.comparison["status"] == "match", arts.comparison


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario_is_deterministic(name):
    if expect_compare.load_expected(name) is None:
        pytest.skip("no snapshot")
    a = run(name, mode="replay", persist=False).result.to_dict()
    b = run(name, mode="replay", persist=False).result.to_dict()
    a.pop("started"); a.pop("ended"); b.pop("started"); b.pop("ended")
    assert a == b
