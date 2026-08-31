"""Central configuration.

Values are read from environment variables (optionally loaded from a local ``.env``)
and an optional ``config.yaml`` in the project root. Environment always wins.

The defaults target the free Cisco DevNet *always-on* sandboxes so a fresh clone can
run in ``replay`` mode with zero setup, and in ``live``/``record`` mode as soon as the
laptop has internet.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = PROJECT_ROOT / "fixtures"
EXPECTED_DIR = PROJECT_ROOT / "expected"
RUNS_DIR = PROJECT_ROOT / "runs"
TOPOLOGIES_DIR = PROJECT_ROOT / "topologies"

Mode = Literal["live", "record", "replay"]

load_dotenv(PROJECT_ROOT / ".env")


def _env(key: str, default: str | None = None) -> str | None:
    val = os.getenv(key)
    return val if val is not None and val != "" else default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class DnacConfig(BaseModel):
    # Cisco DevNet always-on Catalyst Center sandbox (no VPN, no reservation).
    base_url: str = "https://sandboxdnac.cisco.com"
    username: str = "devnetuser"
    password: str = "Cisco123!"
    version: str = "2.3.7.6"
    verify: bool = False  # sandbox presents an internal-CA cert


class IseConfig(BaseModel):
    # Cisco DevNet always-on ISE sandbox (no VPN). Confirm the current ERS
    # credentials on the sandbox page - they are shown there after a free login.
    base_url: str = "https://devnetsandboxise.cisco.com"
    username: str = "readonly"
    password: str = "ISEisC00L"
    ers_username: str = "readonly"
    ers_password: str = "ISEisC00L"
    verify: bool = False


class MerakiConfig(BaseModel):
    api_key: str | None = None
    base_url: str = "https://api.meraki.com/api/v1"


class WlcConfig(BaseModel):
    # Catalyst 9800 wireless LAN controller, queried over RESTCONF
    # (Cisco-IOS-XE-wireless-* YANG models).
    #
    # The DevNet Catalyst 9800 sandbox is *reserved* (book a slot + AnyConnect
    # VPN), not always-on, so this source is opt-in: leave ``enabled`` false and
    # the wireless scenarios keep using Catalyst Center / synthetic RF. Set
    # NETSIM_WLC_ENABLED=true plus the WLC_* vars once you have a reservation,
    # then run the wireless scenarios with --mode record to capture a cassette.
    enabled: bool = False
    base_url: str = "https://10.10.20.51"
    username: str = "developer"
    password: str = "C1sco12345"
    verify: bool = False
    timeout: int = 30


class Settings(BaseModel):
    mode: Mode = "replay"
    topology: str = "topologies/campus-small.yaml"
    dnac: DnacConfig = Field(default_factory=DnacConfig)
    ise: IseConfig = Field(default_factory=IseConfig)
    meraki: MerakiConfig = Field(default_factory=MerakiConfig)
    wlc: WlcConfig = Field(default_factory=WlcConfig)

    def topology_path(self) -> Path:
        p = Path(self.topology)
        return p if p.is_absolute() else PROJECT_ROOT / p


def _load_yaml_overrides() -> dict[str, Any]:
    cfg_file = PROJECT_ROOT / "config.yaml"
    if not cfg_file.exists():
        return {}
    data = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    y = _load_yaml_overrides()
    y_dnac = y.get("dnac", {})
    y_ise = y.get("ise", {})
    y_meraki = y.get("meraki", {})
    y_wlc = y.get("wlc", {})

    dnac = DnacConfig(
        base_url=_env("NETSIM_DNAC_BASE_URL", y_dnac.get("base_url")) or DnacConfig().base_url,
        username=_env("NETSIM_DNAC_USERNAME", y_dnac.get("username")) or DnacConfig().username,
        password=_env("NETSIM_DNAC_PASSWORD", y_dnac.get("password")) or DnacConfig().password,
        version=_env("NETSIM_DNAC_VERSION", y_dnac.get("version")) or DnacConfig().version,
        verify=_env_bool("NETSIM_DNAC_VERIFY", y_dnac.get("verify", DnacConfig().verify)),
    )
    ise = IseConfig(
        base_url=_env("NETSIM_ISE_BASE_URL", y_ise.get("base_url")) or IseConfig().base_url,
        username=_env("NETSIM_ISE_USERNAME", y_ise.get("username")) or IseConfig().username,
        password=_env("NETSIM_ISE_PASSWORD", y_ise.get("password")) or IseConfig().password,
        ers_username=_env("NETSIM_ISE_ERS_USERNAME", y_ise.get("ers_username"))
        or IseConfig().ers_username,
        ers_password=_env("NETSIM_ISE_ERS_PASSWORD", y_ise.get("ers_password"))
        or IseConfig().ers_password,
        verify=_env_bool("NETSIM_ISE_VERIFY", y_ise.get("verify", IseConfig().verify)),
    )
    meraki = MerakiConfig(
        api_key=_env("NETSIM_MERAKI_API_KEY", y_meraki.get("api_key")),
        base_url=_env("NETSIM_MERAKI_BASE_URL", y_meraki.get("base_url")) or MerakiConfig().base_url,
    )
    wlc = WlcConfig(
        enabled=_env_bool("NETSIM_WLC_ENABLED", y_wlc.get("enabled", WlcConfig().enabled)),
        base_url=_env("NETSIM_WLC_BASE_URL", y_wlc.get("base_url")) or WlcConfig().base_url,
        username=_env("NETSIM_WLC_USERNAME", y_wlc.get("username")) or WlcConfig().username,
        password=_env("NETSIM_WLC_PASSWORD", y_wlc.get("password")) or WlcConfig().password,
        verify=_env_bool("NETSIM_WLC_VERIFY", y_wlc.get("verify", WlcConfig().verify)),
        timeout=int(_env("NETSIM_WLC_TIMEOUT", str(y_wlc.get("timeout", WlcConfig().timeout)))
                    or WlcConfig().timeout),
    )
    mode = _env("NETSIM_MODE", y.get("mode")) or "replay"
    topology = _env("NETSIM_TOPOLOGY", y.get("topology")) or Settings().topology
    return Settings(
        mode=mode, topology=topology, dnac=dnac, ise=ise, meraki=meraki, wlc=wlc
    )
