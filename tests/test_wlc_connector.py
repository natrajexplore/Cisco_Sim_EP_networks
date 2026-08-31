"""Catalyst 9800 WLC connector: RESTCONF envelope parsing + RF normalisation.

Runs fully offline - ``requests.Session.get`` is stubbed with canned
``yang-data+json`` payloads, so no cassette and no network are needed.
"""

from __future__ import annotations

import json

import pytest
import requests

from netsimlab.config import get_settings
from netsimlab.connectors.base import ConnectorError
from netsimlab.connectors.wlc import WlcConnector

_CAPWAP = {
    "Cisco-IOS-XE-wireless-access-point-oper:capwap-data": [
        {"wtp-mac": "AA:BB:CC:00:00:01", "name": "ap-floor1-a"},
        {"wtp-mac": "AA:BB:CC:00:00:02", "name": "ap-floor2-a"},
    ]
}
_RRM = {
    "Cisco-IOS-XE-wireless-rrm-oper:rrm-measurement": [
        {
            "wtp-mac": "aa:bb:cc:00:00:01",
            "radio-slot-id": 0,
            "load": {"cca-util-percentage": 72},
            "noise": {"noise-data": [{"noise": -79}, {"noise": -88}]},
            "interference": {"interference-data": [{"int-utilization": 35}]},
        },
        {
            "wtp-mac": "aa:bb:cc:00:00:01",
            "radio-slot-id": 1,
            "load": {"rx-utilization": 12, "tx-utilization": 8},
            "noise": {"noise-data": [{"noise": -95}]},
            "interference": {"interference-data": [{"int-utilization": 4}]},
        },
    ]
}
_RADIO = {
    "Cisco-IOS-XE-wireless-access-point-oper:radio-oper-data": [
        {
            "wtp-mac": "aa:bb:cc:00:00:01",
            "radio-slot-id": 0,
            "phy-ht-cfg": {"cfg-data": {"curr-freq": 6}},
            "ap-auto-rf-dot11-data": {"air-quality": 61},
        }
    ]
}
_CLIENTS = {
    "Cisco-IOS-XE-wireless-client-oper:common-oper-data": [
        {"ap-mac": "aa:bb:cc:00:00:01", "ms-radio-stats": {"most-recent-rssi": -78}},
        {"ap-mac": "aa:bb:cc:00:00:01", "rssi": -66},
    ]
}
_WLANS = {
    "Cisco-IOS-XE-wireless-wlan-cfg:wlan-cfg-entries": {
        "wlan-cfg-entry": [
            {"profile-name": "guest-prof", "wlan-id": 3, "wlan-enable": True,
             "apf-vap-id-data": {"ssid": "GUEST"}},
            {"profile-name": "corp-prof", "wlan-id": 1, "wlan-enable": True,
             "apf-vap-id-data": {"ssid": "CORP"}},
        ]
    }
}

_ROUTES = {
    "capwap-data": _CAPWAP,
    "rrm-measurement": _RRM,
    "radio-oper-data": _RADIO,
    "common-oper-data": _CLIENTS,
    "wlan-cfg-entries": _WLANS,
}


class _FakeResp:
    def __init__(self, payload):
        self.status_code = 200
        self.content = json.dumps(payload).encode()

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        return None


@pytest.fixture
def wlc(monkeypatch):
    monkeypatch.setenv("NETSIM_WLC_ENABLED", "true")
    get_settings.cache_clear()

    def fake_get(self, url, **kwargs):
        for marker, payload in _ROUTES.items():
            if marker in url:
                return _FakeResp(payload)
        return _FakeResp({})

    monkeypatch.setattr(requests.Session, "get", fake_get)
    yield WlcConnector(mode="live", scenario="unit")
    get_settings.cache_clear()


def test_disabled_connector_raises(monkeypatch):
    monkeypatch.setenv("NETSIM_WLC_ENABLED", "false")
    get_settings.cache_clear()
    try:
        with pytest.raises(ConnectorError):
            with WlcConnector(mode="live", scenario="unit").session():
                pass
    finally:
        get_settings.cache_clear()


def test_wlans_and_access_points(wlc):
    with wlc.session() as w:
        wlans = w.wlans()
        aps = w.access_points()
    assert {x["apf-vap-id-data"]["ssid"] for x in wlans} == {"GUEST", "CORP"}
    assert {a["name"] for a in aps} == {"ap-floor1-a", "ap-floor2-a"}


def test_rf_by_ap_shape_and_values(wlc):
    with wlc.session() as w:
        rf = w.rf_by_ap()

    assert set(rf) == {"ap-floor1-a"}  # only AP1 has telemetry
    ap1 = rf["ap-floor1-a"]

    b24 = ap1["band_2_4ghz"]
    assert b24["channel_utilization_pct"] == 72
    assert b24["noise_dbm"] == -79            # least-negative = worst
    assert b24["interference_pct"] == 35
    assert b24["channel"] == 6
    assert b24["air_quality"] == 61

    b5 = ap1["band_5ghz"]
    assert b5["channel_utilization_pct"] == 20  # rx 12 + tx 8
    assert b5["noise_dbm"] == -95

    assert ap1["min_client_rssi_dbm"] == -78   # min across client rows


def test_rf_feeds_assessment(wlc):
    from netsimlab.scenarios.wireless_rf import _assess
    from netsimlab.topology.models import RfProfile

    with wlc.session() as w:
        rf = w.rf_by_ap()["ap-floor1-a"]
    sev = {s for s, _, _ in _assess(rf, RfProfile())}
    assert "warn" in sev and "crit" in sev


def test_missing_metrics_do_not_false_flag(wlc):
    """An AP the WLC returns no RRM/radio data for must not raise or over-report."""
    from netsimlab.scenarios.wireless_rf import _assess
    from netsimlab.topology.models import RfProfile

    partial = {"ap": "x", "band_2_4ghz": {"channel": 1}, "band_5ghz": {}}
    assert _assess(partial, RfProfile()) == []
