from fastapi.testclient import TestClient

from netsimlab.topology.inventory import device_inventory, health_grade, quality_summary
from netsimlab.topology.loader import load_topology
from netsimlab.web.app import app

TOPO = "topologies/campus-small.yaml"


def test_inventory_covers_every_device():
    topo = load_topology(TOPO)
    inv = {d["name"]: d for d in device_inventory(topo)}
    assert set(inv) == {d.name for d in topo.devices}
    acc1 = inv["access-1"]
    ifaces = {p["interface"] for p in acc1["ports"]}
    assert {"GigabitEthernet1/0/10", "GigabitEthernet1/0/20", "GigabitEthernet1/0/48"} <= ifaces
    assert {e["name"] for e in acc1["endpoints"]} == {"emp-laptop-1", "floor1-printer"}
    assert any(n["name"] == "dist-1" for n in acc1["neighbors"])


def test_relaxed_ports_lower_health():
    inv = {d["name"]: d for d in device_inventory(load_topology(TOPO))}
    printer = next(p for p in inv["access-1"]["ports"] if p["interface"] == "GigabitEthernet1/0/20")
    assert printer["verdict"] == "warn"
    assert inv["access-1"]["health"] < 100
    assert inv["core-1"]["health"] == 100
    assert inv["core-1"]["tier"] > inv["access-1"]["tier"] > inv["ap-floor1-a"]["tier"]


def test_quality_summary():
    q = quality_summary(load_topology(TOPO), [])
    assert q["devices"] == 9 and q["endpoints"] == 5
    assert q["ports"]["total"] == q["ports"]["nac"] + q["ports"]["ap"] + q["ports"]["uplink"]
    assert q["worst"][0]["name"] == "access-1"
    assert q["scenarios"]["pass_rate"] is None
    assert health_grade(95) == "good" and health_grade(75) == "fair" and health_grade(10) == "poor"


def test_device_api():
    c = TestClient(app)
    assert c.get("/api/devices").status_code == 200
    assert c.get("/api/devices/core-1").json()["role"] == "core"
    assert c.get("/api/devices/nope").status_code == 404
    assert c.get("/api/quality").json()["devices"] == 9


def test_quality_uses_latest_run_per_scenario():
    runs = [  # newest first, as latest_runs() returns them
        {"scenario": "a", "counts": {"pass": 3, "fail": 1}, "comparison_status": "match"},
        {"scenario": "a", "counts": {"pass": 0, "fail": 9}, "comparison_status": "match"},
        {"scenario": "b", "counts": {"pass": 4, "warn": 0}, "comparison_status": "data-drift"},
    ]
    s = quality_summary(load_topology(TOPO), runs)["scenarios"]
    assert s == {"ran": 2, "pass_rate": 88, "drift": 1}
