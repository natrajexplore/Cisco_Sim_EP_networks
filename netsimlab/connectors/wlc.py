"""Catalyst 9800 Wireless LAN Controller connector.

Talks to an eWLC over **RESTCONF** (``Cisco-IOS-XE-wireless-*`` YANG models)
using plain ``requests`` + HTTP Basic auth. Every exchange goes through the same
``vcrpy`` cassette machinery as the other connectors, so a controller that is
only reachable during a DevNet sandbox reservation can be recorded once and
replayed offline forever.

This source is opt-in (``settings.wlc.enabled``): the always-on DevNet sandboxes
do not include a 9800, so by default the wireless scenarios keep using Catalyst
Center Assurance / synthetic RF.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import requests

from netsimlab.config import get_settings
from netsimlab.connectors.base import Connector, ConnectorError
from netsimlab.connectors.vcr_session import cassette

_SUBDIR = "wlc"
_RESTCONF = "/restconf/data"
_HEADERS = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-data+json",
}

# radio-slot-id -> band label used across the wireless scenarios
_SLOT_BAND = {0: "band_2_4ghz", 1: "band_5ghz", 2: "band_6ghz"}


class WlcConnector(Connector):
    @contextmanager
    def session(self) -> Iterator["WlcConnector"]:
        cfg = get_settings().wlc
        if not cfg.enabled:
            raise ConnectorError(
                "WLC source is disabled - set NETSIM_WLC_ENABLED=true (and the "
                "NETSIM_WLC_* connection vars) to use the Catalyst 9800 connector."
            )
        with cassette(self.mode, _SUBDIR, self.cassette_name):
            sess = requests.Session()
            sess.auth = (cfg.username, cfg.password)
            sess.verify = cfg.verify
            sess.headers.update(_HEADERS)
            self._client = sess
            self._base = cfg.base_url.rstrip("/")
            self._timeout = cfg.timeout
            try:
                yield self
            finally:
                sess.close()
                self._client = None

    # ------------------------------------------------------------------ core
    def _get(self, yang_path: str, **params: Any) -> Any:
        url = f"{self._base}{_RESTCONF}/{yang_path.lstrip('/')}"
        try:
            resp = self._client.get(url, params=params or None, timeout=self._timeout)
        except requests.RequestException as exc:  # noqa: BLE001
            raise ConnectorError(f"WLC RESTCONF request failed ({url}): {exc}") from exc
        if resp.status_code == 401:
            raise ConnectorError("WLC RESTCONF auth failed (401) - check NETSIM_WLC_USERNAME/PASSWORD")
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        if not resp.content:
            return {}
        return resp.json()

    # ------------------------------------------------------------- config
    def wlans(self) -> list[dict[str, Any]]:
        data = self._get("Cisco-IOS-XE-wireless-wlan-cfg:wlan-cfg-data/wlan-cfg-entries")
        entries = _unwrap(data, "wlan-cfg-entries")
        return _as_list(entries.get("wlan-cfg-entry") if isinstance(entries, dict) else entries)

    # -------------------------------------------------------------- oper
    def access_points(self) -> list[dict[str, Any]]:
        data = self._get("Cisco-IOS-XE-wireless-access-point-oper:access-point-oper-data/capwap-data")
        return _as_list(_unwrap(data, "capwap-data"))

    def radio_stats(self) -> list[dict[str, Any]]:
        data = self._get("Cisco-IOS-XE-wireless-access-point-oper:access-point-oper-data/radio-oper-data")
        return _as_list(_unwrap(data, "radio-oper-data"))

    def rrm_measurements(self) -> list[dict[str, Any]]:
        data = self._get("Cisco-IOS-XE-wireless-rrm-oper:rrm-oper-data/rrm-measurement")
        return _as_list(_unwrap(data, "rrm-measurement"))

    def client_summary(self) -> list[dict[str, Any]]:
        data = self._get("Cisco-IOS-XE-wireless-client-oper:client-oper-data/common-oper-data")
        return _as_list(_unwrap(data, "common-oper-data"))

    # ------------------------------------------------------- composed view
    def rf_by_ap(self) -> dict[str, dict[str, Any]]:
        """Return ``{ap_name: rf_dict}`` in the shape the wireless_rf scenario
        expects (bands ``band_2_4ghz`` / ``band_5ghz`` with channel,
        channel_utilization_pct, noise_dbm, interference_pct, air_quality plus a
        top-level ``min_client_rssi_dbm``).

        Missing metrics are simply omitted so the RF assessment skips the checks
        it has no data for rather than flagging false anomalies.
        """
        mac_to_name = {
            str(ap.get("wtp-mac") or ap.get("ap-mac") or "").lower(): ap.get("name")
            for ap in self.access_points()
            if ap.get("name")
        }
        rf: dict[str, dict[str, Any]] = {}

        for m in self.rrm_measurements():
            mac = str(m.get("wtp-mac") or "").lower()
            name = mac_to_name.get(mac)
            if not name:
                continue
            band = _SLOT_BAND.get(_int(m.get("radio-slot-id")), None)
            if band is None:
                continue
            entry = rf.setdefault(name, {"ap": name})
            entry[band] = {**entry.get(band, {}), **_rrm_to_band(m)}

        for r in self.radio_stats():
            mac = str(r.get("wtp-mac") or "").lower()
            name = mac_to_name.get(mac)
            if not name:
                continue
            band = _SLOT_BAND.get(_int(r.get("radio-slot-id")), None)
            if band is None:
                continue
            entry = rf.setdefault(name, {"ap": name})
            merged = {**entry.get(band, {}), **_radio_to_band(r)}
            if merged:
                entry[band] = merged

        for c in self.client_summary():
            name = mac_to_name.get(str(c.get("ap-mac") or "").lower())
            rssi = _int(_dig(c, "ms-radio-stats", "most-recent-rssi")) or _int(c.get("rssi"))
            if name and rssi is not None:
                cur = rf.setdefault(name, {"ap": name}).get("min_client_rssi_dbm")
                rf[name]["min_client_rssi_dbm"] = rssi if cur is None else min(cur, rssi)

        return rf


# --------------------------------------------------------------------- helpers
def _unwrap(payload: Any, leaf: str) -> Any:
    """RESTCONF wraps the answer as ``{"<module>:<leaf>": <value>}``."""
    if isinstance(payload, dict):
        for key, val in payload.items():
            if key.split(":")[-1] == leaf:
                return val
    return payload


def _as_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dig(obj: Any, *keys: str) -> Any:
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def _rrm_to_band(m: dict[str, Any]) -> dict[str, Any]:
    """Map one ``rrm-measurement`` entry to band metrics."""
    out: dict[str, Any] = {}
    load = m.get("load") or {}
    util = _int(load.get("cca-util-percentage"))
    if util is None:
        rx, tx = _int(load.get("rx-utilization")), _int(load.get("tx-utilization"))
        if rx is not None or tx is not None:
            util = (rx or 0) + (tx or 0)
    if util is not None:
        out["channel_utilization_pct"] = util

    noise = _worst_noise(_dig(m, "noise", "noise-data"))
    if noise is not None:
        out["noise_dbm"] = noise

    interference = _dig(m, "interference", "interference-data")
    pct = _sum_pct(interference, "int-utilization")
    if pct is not None:
        out["interference_pct"] = pct

    return out


def _radio_to_band(r: dict[str, Any]) -> dict[str, Any]:
    """Map one ``radio-oper-data`` entry to band metrics."""
    out: dict[str, Any] = {}
    chan = _int(_dig(r, "phy-ht-cfg", "cfg-data", "curr-freq")) or _int(
        _dig(r, "radio-band-info", "0", "phy-ht-cfg", "curr-freq")
    )
    if chan:
        out["channel"] = chan
    air_quality = _int(_dig(r, "ap-auto-rf-dot11-data", "air-quality"))
    if air_quality is not None:
        out["air_quality"] = air_quality
    return {k: v for k, v in out.items() if v is not None}


def _worst_noise(noise_data: Any) -> int | None:
    vals = [
        _int(d.get("noise"))
        for d in _as_list(noise_data)
        if isinstance(d, dict) and _int(d.get("noise")) is not None
    ]
    return max(vals) if vals else None  # least-negative dBm = worst


def _sum_pct(data: Any, key: str) -> int | None:
    vals = [
        _int(d.get(key))
        for d in _as_list(data)
        if isinstance(d, dict) and _int(d.get(key)) is not None
    ]
    return min(sum(vals), 100) if vals else None
