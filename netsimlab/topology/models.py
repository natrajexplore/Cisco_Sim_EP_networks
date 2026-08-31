"""Declarative topology model.

A topology is plain data (YAML) describing a campus/branch: the site hierarchy,
the network devices, the wireless design and the endpoints that will be put through
the NAC / assurance scenarios. Nothing here talks to a controller - it is the
*intent* that scenarios compare real sandbox state against.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

DeviceRole = Literal[
    "core", "distribution", "access", "border", "wlc", "ap", "ise", "catalyst_center", "firewall"
]
AuthMethod = Literal["dot1x", "mab", "guest", "psk", "none"]
Band = Literal["2.4GHz", "5GHz", "6GHz"]


class SiteHierarchy(BaseModel):
    area: str = "Global"
    building: str
    floor: str | None = None

    def path(self) -> str:
        parts = [self.area, self.building] + ([self.floor] if self.floor else [])
        return "/".join(parts)


class Device(BaseModel):
    name: str
    role: DeviceRole
    platform: str = "unknown"
    mgmt_ip: str | None = None
    site: SiteHierarchy | None = None
    # for APs
    wlc: str | None = None
    # free-form expectations checked by the catalyst_provisioning scenario
    expect_reachable: bool = True

    @field_validator("name")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("device name must not be empty")
        return v


class Link(BaseModel):
    a: str
    b: str
    kind: Literal["fiber", "copper", "trunk", "access", "wireless"] = "trunk"
    access_vlan: int | None = None


class Ssid(BaseModel):
    name: str
    security: Literal["open", "wpa2-enterprise", "wpa3-enterprise", "wpa2-psk", "hotspot-guest"]
    auth_method: AuthMethod
    vlan: int | None = None
    band: list[Band] = Field(default_factory=lambda: ["5GHz"])
    portal: str | None = None  # ISE portal name for guest SSIDs
    policy: str | None = None  # references Policy.name


class Policy(BaseModel):
    name: str
    kind: Literal["authc", "authz", "profiler", "posture", "sgt"]
    match: dict[str, str] = Field(default_factory=dict)
    result: dict[str, str] = Field(default_factory=dict)


class Endpoint(BaseModel):
    name: str
    mac: str
    kind: Literal["workstation", "printer", "phone", "iot", "byod", "guest", "ap"] = "workstation"
    connects_to: str  # device name (access switch) or SSID name
    port: str | None = None
    auth_method: AuthMethod = "dot1x"
    identity: str | None = None  # username / cert CN
    expected_vlan: int | None = None
    expected_sgt: str | None = None
    expected_authz_profile: str | None = None
    # attribute bag used by the profiling scenario
    attributes: dict[str, str] = Field(default_factory=dict)

    @field_validator("mac")
    @classmethod
    def _norm_mac(cls, v: str) -> str:
        hexs = "".join(c for c in v.lower() if c in "0123456789abcdef")
        if len(hexs) != 12:
            raise ValueError(f"invalid MAC: {v!r}")
        return ":".join(hexs[i : i + 2] for i in range(0, 12, 2))


class RfProfile(BaseModel):
    """Expected healthy RF envelope for the wireless_rf scenario."""

    max_channel_utilization_pct: int = 60
    min_air_quality: int = 70
    max_noise_dbm: int = -85
    max_interference_pct: int = 30
    coverage_hole_rssi_dbm: int = -75


class Topology(BaseModel):
    name: str
    description: str = ""
    devices: list[Device]
    links: list[Link] = Field(default_factory=list)
    ssids: list[Ssid] = Field(default_factory=list)
    policies: list[Policy] = Field(default_factory=list)
    endpoints: list[Endpoint] = Field(default_factory=list)
    rf_profile: RfProfile = Field(default_factory=RfProfile)

    def device(self, name: str) -> Device | None:
        return next((d for d in self.devices if d.name == name), None)

    def ssid(self, name: str) -> Ssid | None:
        return next((s for s in self.ssids if s.name == name), None)

    def policy(self, name: str) -> Policy | None:
        return next((p for p in self.policies if p.name == name), None)

    def devices_by_role(self, role: DeviceRole) -> list[Device]:
        return [d for d in self.devices if d.role == role]
