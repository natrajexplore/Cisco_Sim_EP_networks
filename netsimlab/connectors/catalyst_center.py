"""Catalyst Center (DNA Center) connector.

Authenticates with the official ``dnacentersdk`` and issues intent-API calls
through the SDK's version-independent ``custom_caller`` so recorded cassettes
stay stable across SDK/controller versions.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from dnacentersdk import DNACenterAPI

from netsimlab.config import get_settings
from netsimlab.connectors.base import Connector, ConnectorError
from netsimlab.connectors.vcr_session import cassette

_SUBDIR = "catalyst_center"


class CatalystCenterConnector(Connector):
    @contextmanager
    def session(self) -> Iterator["CatalystCenterConnector"]:
        cfg = get_settings().dnac
        with cassette(self.mode, _SUBDIR, self.cassette_name):
            try:
                self._client = DNACenterAPI(
                    username=cfg.username,
                    password=cfg.password,
                    base_url=cfg.base_url,
                    version=cfg.version,
                    verify=cfg.verify,
                    single_request_timeout=30,
                )
            except Exception as exc:  # noqa: BLE001
                raise ConnectorError(f"Catalyst Center auth failed: {exc}") from exc
            try:
                yield self
            finally:
                self._client = None

    def _get(self, path: str, **params: Any) -> Any:
        resp = self._client.custom_caller.call_api(
            "GET", path, original_response=True, params=params or None
        )
        resp.raise_for_status()
        return resp.json()

    # --- inventory / design -------------------------------------------------
    def sites(self) -> Any:
        return self._get("/dna/intent/api/v1/site")

    def devices(self) -> Any:
        return self._get("/dna/intent/api/v1/network-device")

    def device_count(self) -> Any:
        return self._get("/dna/intent/api/v1/network-device/count")

    def physical_topology(self) -> Any:
        return self._get("/dna/intent/api/v1/topology/physical-topology")

    def software_images(self) -> Any:
        return self._get("/dna/intent/api/v1/image/importation")

    # --- assurance --------------------------------------------------------
    @staticmethod
    def _bucket_ts() -> int:
        return (int(time.time() * 1000) // 300_000) * 300_000

    def network_health(self) -> Any:
        return self._get("/dna/intent/api/v1/network-health", timestamp=self._bucket_ts())

    def client_health(self) -> Any:
        # timestamp must land on a 5-minute epoch-ms boundary or ISE/DNAC 400s.
        return self._get("/dna/intent/api/v1/client-health", timestamp=self._bucket_ts())

    def issues(self) -> Any:
        return self._get("/dna/intent/api/v1/issues")

    def ap_rf_stats(self) -> Any:
        """AP-facing RF: fall back through the endpoints that exist on the sandbox."""
        try:
            return self._get(
                "/dna/intent/api/v1/device-health",
                deviceRole="AP",
            )
        except Exception:  # noqa: BLE001
            return self._get("/dna/intent/api/v1/network-device", family="Unified AP")

    def wireless_ssids(self) -> Any:
        return self._get("/dna/intent/api/v1/wireless/profile")
