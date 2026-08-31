"""Render a run to a standalone HTML report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(["html", "j2"]),
)


def render_report(run_id: str, result: dict[str, Any], comparison: dict[str, Any]) -> str:
    tpl = _env.get_template("report.html.j2")
    return tpl.render(run_id=run_id, result=result, comparison=comparison)


def write_report(directory: Path, run_id: str, result: dict[str, Any], comparison: dict[str, Any]) -> Path:
    html = render_report(run_id, result, comparison)
    out = directory / "report.html"
    out.write_text(html, encoding="utf-8")
    return out
