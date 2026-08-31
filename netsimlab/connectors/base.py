"""Shared connector types."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from netsimlab.config import Mode


@dataclass
class ConnectorError(Exception):
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


@dataclass
class Connector:
    """Base class for the DevNet sandbox connectors.

    ``mode``:
      * ``live``   - call the always-on sandbox, no recording
      * ``record`` - call the sandbox and write every HTTP exchange to a cassette
      * ``replay`` - serve responses from the cassette, no network
    """

    mode: Mode = "replay"
    scenario: str = "default"
    _client: Any = field(default=None, init=False, repr=False)

    @property
    def cassette_name(self) -> str:
        return f"{self.scenario}.yaml"

    @contextmanager
    def session(self) -> Iterator["Connector"]:  # pragma: no cover - overridden
        yield self
