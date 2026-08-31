"""NAC / AP switchport rule checker + running-config parsing."""

from __future__ import annotations

from netsimlab import port_eval
from netsimlab.apiutil import interface_block, nac_config_flags
from netsimlab.topology.loader import load_topology
from netsimlab.topology.models import AccessPort, Endpoint

TOPO = "topologies/campus-small.yaml"


def _codes(findings):
    return {f.code for f in findings}


def test_locked_down_nac_port_is_clean():
    p = AccessPort(switch="a", interface="Gi1/0/1", data_vlan=20)
    assert port_eval.evaluate_nac_port(p) == []
    assert port_eval.verdict_for([]) == "pass"


def test_open_multihost_no_coa_flags_crit_and_warn():
    p = AccessPort(
        switch="a", interface="Gi1/0/2", mode="open", host_mode="multi-host",
        methods=["mab"], order="mab-first", reauth=False, coa=False, dacl=False,
    )
    f = port_eval.evaluate_nac_port(p)
    assert "no-coa" in _codes(f)
    assert "open-mode" in _codes(f)
    assert "multi-host" in _codes(f)
    assert port_eval.verdict_for(f) == "fail"  # no-coa is crit


def test_single_host_with_voice_is_critical():
    p = AccessPort(switch="a", interface="Gi1/0/3", host_mode="single-host", voice_vlan=40)
    assert "single-host-voice" in _codes(port_eval.evaluate_nac_port(p))


def test_nac_on_trunk_is_critical():
    p = AccessPort(switch="a", interface="Te1/1/1", trunk=True)
    assert "nac-on-trunk" in _codes(port_eval.evaluate_nac_port(p))


def test_non_supplicant_without_mab_fallback():
    p = AccessPort(switch="a", interface="Gi1/0/4", methods=["dot1x"])
    printer = Endpoint(name="p1", mac="00:11:22:33:44:55", kind="printer", connects_to="a")
    assert "no-mab-fallback" in _codes(port_eval.evaluate_nac_port(p, printer))


def test_ap_port_poe_and_qos():
    p = AccessPort(switch="a", interface="Gi1/0/48", purpose="ap", trunk=True,
                   trunk_allowed_vlans=[10, 100], poe=False, qos_trust="none")
    f = port_eval.evaluate_ap_port(p)
    assert _codes(f) == {"no-poe", "no-qos-trust"}
    assert port_eval.verdict_for(f) == "warn"


def test_uplink_port_rejects_auth():
    p = AccessPort(switch="a", interface="Te1/1/1", purpose="uplink", trunk=True,
                   methods=["dot1x"])
    assert "nac-on-uplink" in _codes(port_eval.evaluate_uplink_port(p))


def test_ap_purpose_clears_default_methods():
    assert AccessPort(switch="a", interface="Gi1/0/48", purpose="ap").methods == []
    # explicit methods are kept
    assert AccessPort(switch="a", interface="Gi1/0/48", purpose="ap",
                      methods=["mab"]).methods == ["mab"]


def test_topology_derives_and_merges_ports():
    topo = load_topology(TOPO)
    ports = topo.effective_access_ports()
    keys = {p.key for p in ports}
    assert ("access-1", "GigabitEthernet1/0/10") in keys   # from endpoint + explicit
    assert ("access-1", "GigabitEthernet1/0/48") in keys   # AP link
    assert ("access-1", "TenGigabitEthernet1/1/1") in keys  # uplink to dist-1

    printer_port = topo.access_port("access-1", "GigabitEthernet1/0/20")
    assert printer_port.mode == "open"  # explicit override, not the derived default


CONFIG = """\
interface GigabitEthernet1/0/10
 switchport access vlan 20
 switchport mode access
 access-session host-mode multi-auth
 access-session closed
 access-session port-control auto
 mab
 dot1x pae authenticator
 authentication periodic
 service-policy type control subscriber DOT1X_MAB
!
interface GigabitEthernet1/0/2
 switchport mode access
!
"""


def test_interface_block_and_flag_parsing():
    block = interface_block(CONFIG, "Gi1/0/10")
    assert "mab" in block
    flags = nac_config_flags(block)
    assert flags["dot1x"] is True
    assert flags["mab"] is True
    assert flags["port_control_auto"] is True
    assert flags["host_mode"] == "multi-auth"
    assert flags["mode"] == "closed"
    assert flags["reauth"] is True

    assert interface_block(CONFIG, "Gi1/0/2").strip() == "switchport mode access"
