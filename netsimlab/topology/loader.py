"""Load a topology YAML file into the :class:`Topology` model."""

from __future__ import annotations

from pathlib import Path

import yaml

from netsimlab.config import PROJECT_ROOT
from netsimlab.topology.models import Topology


def load_topology(path: str | Path) -> Topology:
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"topology file not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"topology file {p} must contain a mapping at the top level")
    return Topology.model_validate(data)
