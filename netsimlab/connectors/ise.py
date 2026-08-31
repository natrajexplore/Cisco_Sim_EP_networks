"""Identity Services Engine connector.

Uses the official ``ciscoisesdk`` for the ERS session, then issues calls through
``custom_caller``. ERS endpoints return JSON when the ``Accept: application/json``
header is set (the SDK does this).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from ciscoisesdk import IdentityServicesEngineAPI

from netsimlab.config import get_settings
from netsimlab.connectors.base import Connector, ConnectorError
from netsimlab.connectors.vcr_session import cassette

_SUBDIR = "ise"


class IseConnector(Connector):
    @contextmanager
    def session(self) -> Iterator["IseConnector"]:
        cfg = get_settings().ise
        with cassette(self.mode, _SUBDIR, self.cassette_name):
            try:
                self._client = IdentityServicesEngineAPI(
                    username=cfg.ers_username,
                    password=cfg.ers_password,
                    base_url=cfg.base_url,
                    ui_base_url=cfg.base_url,
                    ers_base_url=cfg.base_url,
                    mnt_base_url=cfg.base_url,
                    px_grid_base_url=cfg.base_url,
                    version="3.1_Patch_1",
                    uses_api_gateway=False,
                    verify=cfg.verify,
                    single_request_timeout=30,
                )
            except Exception as exc:  # noqa: BLE001
                raise ConnectorError(f"ISE ERS auth failed: {exc}") from exc
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

    # --- network access devices -----------------------------------------
    def network_devices(self) -> Any:
        return self._get("/ers/config/networkdevice")

    def network_device_groups(self) -> Any:
        return self._get("/ers/config/networkdevicegroup")

    # --- identities ----------------------------------------------------
    def internal_users(self) -> Any:
        return self._get("/ers/config/internaluser")

    def identity_groups(self) -> Any:
        return self._get("/ers/config/identitygroup")

    def endpoints(self) -> Any:
        return self._get("/ers/config/endpoint")

    def endpoint_groups(self) -> Any:
        return self._get("/ers/config/endpointgroup")

    # --- policy building blocks --------------------------------------
    def authorization_profiles(self) -> Any:
        return self._get("/ers/config/authorizationprofile")

    def downloadable_acls(self) -> Any:
        return self._get("/ers/config/downloadableacl")

    def sgts(self) -> Any:
        return self._get("/ers/config/sgt")

    def allowed_protocols(self) -> Any:
        return self._get("/ers/config/allowedprotocols")

    # --- guest -------------------------------------------------------
    def guest_types(self) -> Any:
        return self._get("/ers/config/guesttype")

    def portals(self) -> Any:
        return self._get("/ers/config/portal")

    def sponsor_portals(self) -> Any:
        return self._get("/ers/config/sponsorportal")
