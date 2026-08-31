"""``netsim`` command line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from netsimlab.config import get_settings
from netsimlab.expect import compare as expect_compare
from netsimlab.report.html import write_report
from netsimlab.runner import latest_runs, load_run, run as run_scenario
from netsimlab.scenarios.registry import list_scenarios
from netsimlab.topology.diagram import to_graph_json, to_mermaid
from netsimlab.topology.graph import validate
from netsimlab.topology.loader import load_topology

app = typer.Typer(add_completion=False, help="Lightweight Cisco ISE/NAC + wireless + Catalyst Center scenario lab.")
topology_app = typer.Typer(help="Inspect and validate topology files.")
scenario_app = typer.Typer(help="List and run scenarios.")
snapshot_app = typer.Typer(help="Manage golden 'expected output' snapshots.")
app.add_typer(topology_app, name="topology")
app.add_typer(scenario_app, name="scenario")
app.add_typer(snapshot_app, name="snapshot")

console = Console()
_VERDICT_STYLE = {"pass": "green", "fail": "bold red", "warn": "yellow", "info": "cyan"}


@app.callback()
def _root() -> None:
    """netsim - drive real Cisco DevNet sandboxes (or replay them offline)."""


# --------------------------------------------------------------------------- topology
@topology_app.command("validate")
def topology_validate(file: Optional[str] = typer.Argument(None)) -> None:
    path = file or get_settings().topology
    topo = load_topology(path)
    rep = validate(topo)
    for w in rep.warnings:
        console.print(f"[yellow]warn[/]  {w}")
    for e in rep.errors:
        console.print(f"[bold red]error[/] {e}")
    if rep.ok:
        console.print(f"[green]OK[/] {topo.name}: {len(topo.devices)} devices, "
                      f"{len(topo.endpoints)} endpoints, {len(topo.ssids)} SSIDs, {len(topo.policies)} policies")
    else:
        raise typer.Exit(code=1)


@topology_app.command("show")
def topology_show(file: Optional[str] = typer.Argument(None)) -> None:
    topo = load_topology(file or get_settings().topology)
    t = Table(title=f"{topo.name} — devices")
    t.add_column("name"); t.add_column("role"); t.add_column("platform"); t.add_column("site")
    for d in topo.devices:
        t.add_row(d.name, d.role, d.platform, d.site.path() if d.site else "-")
    console.print(t)
    e = Table(title="endpoints")
    e.add_column("name"); e.add_column("kind"); e.add_column("auth"); e.add_column("connects_to"); e.add_column("expect")
    for ep in topo.endpoints:
        exp = ", ".join(f"{k}={v}" for k, v in {
            "vlan": ep.expected_vlan, "sgt": ep.expected_sgt, "authz": ep.expected_authz_profile
        }.items() if v)
        e.add_row(ep.name, ep.kind, ep.auth_method, ep.connects_to, exp or "-")
    console.print(e)


@topology_app.command("diagram")
def topology_diagram(
    file: Optional[str] = typer.Argument(None),
    fmt: str = typer.Option("mermaid", "--format", "-f", help="mermaid | json"),
    out: Optional[Path] = typer.Option(None, "--out", "-o"),
) -> None:
    topo = load_topology(file or get_settings().topology)
    text = to_mermaid(topo) if fmt == "mermaid" else json.dumps(to_graph_json(topo), indent=2)
    if out:
        out.write_text(text, encoding="utf-8")
        console.print(f"[green]wrote[/] {out}")
    else:
        console.print(text, markup=False, highlight=False)


# --------------------------------------------------------------------------- scenario
@scenario_app.command("list")
def scenario_list() -> None:
    t = Table(title="scenarios")
    t.add_column("name"); t.add_column("title"); t.add_column("requires"); t.add_column("description")
    for s in list_scenarios():
        t.add_row(s.name, s.title, ",".join(s.requires), s.description)
    console.print(t)


@scenario_app.command("run")
def scenario_run(
    name: str = typer.Argument(...),
    mode: Optional[str] = typer.Option(None, "--mode", "-m", help="live | record | replay"),
    topology: Optional[str] = typer.Option(None, "--topology", "-t"),
    report: bool = typer.Option(True, "--report/--no-report"),
) -> None:
    settings = get_settings()
    eff_mode = mode or settings.mode
    console.print(Panel.fit(f"[b]{name}[/]  mode=[b]{eff_mode}[/]  topology=[b]{topology or settings.topology}[/]"))

    def _echo(step) -> None:
        style = _VERDICT_STYLE.get(step.verdict, "white")
        console.print(f"[{style}]{step.verdict.upper():5}[/] {step.name}")
        if step.summary:
            console.print(f"       [dim]{step.summary}[/]")
        for n in step.notes:
            console.print(f"       [dim]· {n}[/]")

    arts = run_scenario(name, mode=eff_mode, topology_path=topology, on_step=_echo, persist=True)  # type: ignore[arg-type]
    if report:
        rp = write_report(arts.directory, arts.run_id, arts.result.to_dict(), arts.comparison)
        console.print(f"[green]report[/] {rp}")

    c = arts.result.counts
    console.print(
        f"\n[b]{arts.result.title}[/]: "
        f"[green]{c['pass']} pass[/] · [bold red]{c['fail']} fail[/] · "
        f"[yellow]{c['warn']} warn[/] · [cyan]{c['info']} info[/]  "
        f"| snapshot: [b]{arts.comparison['status']}[/]  | run {arts.run_id}"
    )
    if not arts.result.ok:
        raise typer.Exit(code=1)


# --------------------------------------------------------------------------- runs
@app.command("report")
def report_cmd(run_id: str = typer.Argument(...)) -> None:
    data = load_run(run_id)
    from netsimlab.config import RUNS_DIR

    rp = write_report(RUNS_DIR / run_id, run_id, data["result"], data["comparison"])
    console.print(f"[green]wrote[/] {rp}")


@app.command("runs")
def runs_cmd(limit: int = typer.Option(20, "--limit", "-n")) -> None:
    t = Table(title="recent runs")
    for col in ("run_id", "scenario", "mode", "ok", "pass/fail/warn", "snapshot"):
        t.add_column(col)
    for r in latest_runs(limit):
        c = r["counts"] or {}
        t.add_row(
            r["run_id"], r["scenario"], r["mode"], str(r["ok"]),
            f"{c.get('pass', 0)}/{c.get('fail', 0)}/{c.get('warn', 0)}",
            str(r["comparison_status"]),
        )
    console.print(t)


# --------------------------------------------------------------------------- snapshot
@snapshot_app.command("save")
def snapshot_save(
    name: str = typer.Argument(...),
    mode: str = typer.Option("record", "--mode", "-m"),
    topology: Optional[str] = typer.Option(None, "--topology", "-t"),
) -> None:
    """Run the scenario and store its result as the golden 'expected output'."""
    arts = run_scenario(name, mode=mode, topology_path=topology, persist=True)  # type: ignore[arg-type]
    p = expect_compare.save_expected(name, arts.result.to_dict())
    console.print(f"[green]saved snapshot[/] {p}  ({arts.result.counts})")


@snapshot_app.command("show")
def snapshot_show(name: str = typer.Argument(...)) -> None:
    exp = expect_compare.load_expected(name)
    if exp is None:
        console.print(f"[yellow]no snapshot for {name}[/]")
        raise typer.Exit(code=1)
    console.print_json(data=exp)


# --------------------------------------------------------------------------- sandbox
@app.command("sandbox")
def sandbox_check() -> None:
    """Check reachability of the configured DevNet always-on sandboxes."""
    import requests

    s = get_settings()
    urllib3 = __import__("urllib3")
    urllib3.disable_warnings()
    targets = [
        ("Catalyst Center", s.dnac.base_url, s.dnac.verify, None),
        (
            "ISE ERS",
            s.ise.base_url + "/ers/config/networkdevice",
            s.ise.verify,
            (s.ise.ers_username, s.ise.ers_password),
        ),
    ]
    if s.wlc.enabled:
        targets.append(
            (
                "Catalyst 9800 WLC",
                s.wlc.base_url.rstrip("/")
                + "/restconf/data/Cisco-IOS-XE-wireless-general-cfg:general-cfg-data",
                s.wlc.verify,
                (s.wlc.username, s.wlc.password),
            )
        )
    t = Table(title="DevNet sandbox reachability")
    t.add_column("system"); t.add_column("endpoint"); t.add_column("status")
    for label, url, verify, auth in targets:
        try:
            r = requests.get(url, timeout=15, verify=verify, auth=auth,
                             headers={"Accept": "application/json"})
            colour = "green" if r.status_code < 400 else "yellow"
            hint = " (auth failed - update .env)" if r.status_code in (401, 403) else ""
            t.add_row(label, url, f"[{colour}]HTTP {r.status_code}{hint}[/]")
        except Exception as exc:  # noqa: BLE001
            t.add_row(label, url, f"[red]{type(exc).__name__}[/]")
    console.print(t)
    console.print(f"[dim]mode={s.mode}  topology={s.topology}[/]")


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8080, reload: bool = False) -> None:
    """Start the web dashboard."""
    import uvicorn

    uvicorn.run("netsimlab.web.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
