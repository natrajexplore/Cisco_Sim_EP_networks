from netsimlab.nac_eval import check_expectations, evaluate
from netsimlab.topology.diagram import to_graph_json, to_mermaid
from netsimlab.topology.graph import validate
from netsimlab.topology.loader import load_topology

TOPO = "topologies/campus-small.yaml"


def test_topology_loads_and_validates():
    topo = load_topology(TOPO)
    rep = validate(topo)
    assert rep.ok, rep.errors
    assert topo.device("core-1").role == "core"
    assert len(topo.devices_by_role("ap")) == 2


def test_mac_normalisation():
    topo = load_topology(TOPO)
    ep = next(e for e in topo.endpoints if e.name == "emp-laptop-1")
    assert ep.mac == "00:1a:2b:3c:4d:5e"


def test_diagram_outputs():
    topo = load_topology(TOPO)
    assert to_mermaid(topo).startswith("graph TD")
    gj = to_graph_json(topo)
    assert gj["nodes"] and gj["edges"]


def test_nac_eval_employee_dot1x():
    topo = load_topology(TOPO)
    ep = next(e for e in topo.endpoints if e.name == "emp-laptop-1")
    dec = evaluate(topo, ep, kind="authz")
    assert dec.matched_policy == "Employee-Wired-Dot1x"
    assert dec.vlan == "20"
    verdict, _ = check_expectations(ep, dec)
    assert verdict == "pass"


def test_nac_eval_printer_mab():
    topo = load_topology(TOPO)
    ep = next(e for e in topo.endpoints if e.name == "floor1-printer")
    dec = evaluate(topo, ep, kind="authz")
    assert dec.matched_policy == "Printer-MAB"
    assert dec.dacl == "PRINT_ONLY"


def test_guest_pre_and_post_auth():
    topo = load_topology(TOPO)
    ep = next(e for e in topo.endpoints if e.name == "guest-phone-1")
    pre = ep.model_copy(deep=True)
    pre.attributes = {"portal_state": "pre-auth"}
    assert evaluate(topo, pre, kind="authz").url_redirect == "GuestPortal"
    post = ep.model_copy(deep=True)
    post.attributes = {"portal_state": "authenticated"}
    assert evaluate(topo, post, kind="authz").matched_policy == "Guest-Permit"
