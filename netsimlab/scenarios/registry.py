"""Scenario registry."""

from __future__ import annotations

from netsimlab.scenarios.base import Scenario
from netsimlab.scenarios.catalyst_provisioning import CatalystProvisioning
from netsimlab.scenarios.guest_wireless import GuestWireless
from netsimlab.scenarios.profiling_posture import ProfilingPosture
from netsimlab.scenarios.wired_dot1x_mab import WiredDot1xMab
from netsimlab.scenarios.wireless_rf import WirelessRf

_SCENARIOS: list[type[Scenario]] = [
    WiredDot1xMab,
    GuestWireless,
    ProfilingPosture,
    CatalystProvisioning,
    WirelessRf,
]

REGISTRY: dict[str, type[Scenario]] = {s.name: s for s in _SCENARIOS}


def get_scenario(name: str) -> Scenario:
    try:
        return REGISTRY[name]()
    except KeyError:
        raise KeyError(
            f"unknown scenario {name!r}. Available: {', '.join(sorted(REGISTRY))}"
        ) from None


def list_scenarios() -> list[Scenario]:
    return [cls() for cls in _SCENARIOS]
