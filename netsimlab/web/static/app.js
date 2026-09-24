const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const el = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const getJSON = async (u) => (await fetch(u)).json();

const NODE_COLOR = {
  catalyst_center: "#6f42c1", ise: "#d63384", core: "#0b5cad", distribution: "#1f7a8c",
  access: "#2a9d8f", wlc: "#e76f51", ap: "#f4a261", firewall: "#c1121f", border: "#c1121f",
  ssid: "#8d99ae", endpoint: "#adb5bd",
};
const HEALTH_COLOR = { good: "#2f9e55", fair: "#e0a100", poor: "#d64545", none: "#8d99ae" };
const LINK_COLOR = {
  fiber: "#4dabf7", trunk: "#20c997", copper: "#adb5bd", access: "#adb5bd", wireless: "#f4a261",
  capwap: "#e76f51", endpoint: "#868e96", broadcast: "#8d99ae", mgmt: "#b197fc",
};
const ROLE_LABEL = {
  catalyst_center: "Catalyst Center", ise: "ISE", core: "Core", distribution: "Distribution",
  access: "Access", wlc: "WLC", ap: "AP", firewall: "Firewall", border: "Border",
  ssid: "SSID", endpoint: "Endpoint",
};
// vertical layer for nodes without an inventory entry (SSIDs / endpoints)
const KIND_TIER = { ssid: 1, endpoint: 0 };
const TIER_NAME = ["Endpoints", "Wireless edge", "Access", "Distribution / WLC", "Core", "Controllers"];

let GRAPH = { nodes: [], edges: [] };
let DEVICES = {};          // name -> inventory entry
let VIEW = "2d";
let net2d = null, net3d = null;

function nodeById(id) { return GRAPH.nodes.find((n) => n.id === id); }
function colorBy() { return $("#color-by").value; }
function nodeColor(n) {
  if (colorBy() === "health") {
    const d = DEVICES[n.id];
    return HEALTH_COLOR[d ? d.grade : "none"];
  }
  return NODE_COLOR[n.role] || NODE_COLOR[n.kind] || "#888";
}
function nodeTier(n) {
  const d = DEVICES[n.id];
  return d ? d.tier : (KIND_TIER[n.kind] ?? 2);
}

// ---------------------------------------------------------------- environment

async function loadEnv() {
  const s = await getJSON("/api/settings");
  $("#env").textContent =
    `mode=${s.mode} · dnac=${s.dnac_base_url} · ise=${s.ise_base_url}` +
    (s.wlc_enabled ? ` · wlc=${s.wlc_base_url}` : "");
  $("#mode").value = s.mode;
}

// ---------------------------------------------------------------- quality KPIs

async function loadQuality() {
  const q = await getJSON("/api/quality");
  const ring = $("#health-ring");
  ring.style.setProperty("--pct", q.health);
  ring.style.setProperty("--ring", HEALTH_COLOR[q.grade]);
  $("#health-val").textContent = q.health;
  $("#health-grade").textContent =
    `${q.grade} · ${q.validation.errors} validation error(s), ${q.validation.warnings} warning(s)`;
  $("#k-devices").textContent = q.devices;
  $("#k-roles").textContent = Object.entries(q.by_role)
    .map(([r, n]) => `${n} ${ROLE_LABEL[r] || r}`).join(" · ");
  $("#k-endpoints").textContent = q.endpoints;
  $("#k-ssids").textContent = `${q.ssids} SSID(s) · ${q.links} link(s)`;
  $("#k-ports").textContent = `${q.ports.compliant}/${q.ports.total}`;
  $("#k-ports-bar").style.width = q.ports.total ? `${(100 * q.ports.compliant) / q.ports.total}%` : "0";
  $("#k-crit").textContent = q.findings.crit;
  $("#k-warn").textContent = q.findings.warn;
  $("#k-info").textContent = q.findings.info;
  $("#k-pass").textContent = q.scenarios.pass_rate == null ? "—" : `${q.scenarios.pass_rate}%`;
  $("#k-drift").textContent = q.scenarios.ran
    ? `${q.scenarios.ran} scenario(s) run · ${q.scenarios.drift} drifting`
    : "no runs yet";

  $("#worst").innerHTML = q.worst.filter((w) => w.health < 100).map((w) =>
    `<li><a href="#" data-dev="${esc(w.name)}">${esc(w.name)}</a>
       <span class="muted">${esc(ROLE_LABEL[w.role] || w.role)}</span>
       ${healthBar(w.health)}</li>`).join("") || `<li class="muted">all devices healthy</li>`;
}

function healthBar(h) {
  const g = h >= 90 ? "good" : h >= 70 ? "fair" : "poor";
  return `<span class="hbar ${g}" title="health ${h}/100"><span class="track"><i style="width:${h}%"></i></span><b>${h}</b></span>`;
}

// ---------------------------------------------------------------- device access

const DEV_SORT = { key: "health", dir: 1 };

async function loadDevices() {
  const list = await getJSON("/api/devices");
  DEVICES = Object.fromEntries(list.map((d) => [d.name, d]));
  const roles = [...new Set(list.map((d) => d.role))].sort();
  $("#dev-role").innerHTML = `<option value="">all roles</option>` +
    roles.map((r) => `<option value="${esc(r)}">${esc(ROLE_LABEL[r] || r)}</option>`).join("");
  renderDevices();
}

function renderDevices() {
  const q = $("#dev-filter").value.trim().toLowerCase();
  const role = $("#dev-role").value;
  const val = (d, k) => k === "ports" ? d.ports.length : k === "endpoints" ? d.endpoints.length : (d[k] ?? "");
  const rows = Object.values(DEVICES)
    .filter((d) => !role || d.role === role)
    .filter((d) => !q || [d.name, d.mgmt_ip, d.platform, d.site, d.role].some((v) => (v || "").toLowerCase().includes(q)))
    .sort((a, b) => {
      const x = val(a, DEV_SORT.key), y = val(b, DEV_SORT.key);
      return (typeof x === "number" ? x - y : String(x).localeCompare(String(y))) * DEV_SORT.dir;
    });
  $("#devices tbody").innerHTML = rows.map((d) => `
    <tr data-dev="${esc(d.name)}" tabindex="0">
      <td><span class="dot" style="background:${NODE_COLOR[d.role] || "#888"}"></span><b>${esc(d.name)}</b>
        <div class="muted small">${esc(d.platform)}${d.site ? " · " + esc(d.site) : ""}</div></td>
      <td>${esc(ROLE_LABEL[d.role] || d.role)}</td>
      <td class="mono">${esc(d.mgmt_ip || "—")}</td>
      <td>${d.ports.length || "—"}${d.counts.crit || d.counts.warn
        ? ` <span class="sev crit sm">${d.counts.crit || ""}</span><span class="sev warn sm">${d.counts.warn || ""}</span>` : ""}</td>
      <td>${d.endpoints.length || "—"}</td>
      <td>${healthBar(d.health)}</td>
    </tr>`).join("") || `<tr><td colspan="6" class="muted">no matching devices</td></tr>`;
  $$("#devices th").forEach((th) =>
    th.classList.toggle("sorted", th.dataset.sort === DEV_SORT.key));
}

function kv(label, value, mono) {
  if (value == null || value === "") return "";
  return `<div class="kv"><span>${esc(label)}</span><b class="${mono ? "mono" : ""}">${esc(value)}</b></div>`;
}
function yn(b) { return b ? `<span class="ok">✓</span>` : `<span class="no">✗</span>`; }
function copyBtn(text) { return `<button class="copy ghost" data-copy="${esc(text)}" title="Copy">copy</button>`; }

function openDevice(name) {
  const d = DEVICES[name];
  if (!d) {
    // SSIDs / endpoints: show the hover summary only
    hoverNodeInfo(name);
    return;
  }
  $("#dr-name").innerHTML = `<span class="dot" style="background:${NODE_COLOR[d.role] || "#888"}"></span>${esc(d.name)}`;
  $("#dr-sub").textContent = [ROLE_LABEL[d.role] || d.role, d.platform, d.site].filter(Boolean).join(" · ");

  const sshCmd = d.mgmt_ip ? `ssh admin@${d.mgmt_ip}` : null;
  const showCmds = [];
  if (d.role === "access" || d.role === "distribution") {
    showCmds.push("show access-session", "show authentication sessions", "show device-tracking database",
      "show power inline", "show cdp neighbors detail");
    d.ports.filter((p) => p.purpose === "nac").forEach((p) =>
      showCmds.push(`show access-session interface ${p.interface} details`));
  } else if (d.role === "wlc") {
    showCmds.push("show ap summary", "show wlan summary", "show wireless client summary", "show ap dot11 5ghz summary");
  } else if (d.role === "core") {
    showCmds.push("show ip route summary", "show interfaces status", "show cdp neighbors");
  } else if (d.role === "ap") {
    showCmds.push("show capwap client rcb", "show dot11 wlan");
  }

  const ports = d.ports.map((p) => {
    const vlan = p.trunk
      ? `trunk ${p.trunk_allowed_vlans.length ? p.trunk_allowed_vlans.join(",") : "all"}`
      : [p.data_vlan && `data ${p.data_vlan}`, p.voice_vlan && `voice ${p.voice_vlan}`].filter(Boolean).join(" / ");
    const auth = p.purpose === "nac"
      ? `${p.mode} · ${p.host_mode}<br><span class="muted">${p.methods.join("+") || "none"}${p.order ? " · " + p.order : ""}</span>`
      : `<span class="muted">PoE ${p.poe ? "on" : "off"} · QoS ${p.qos_trust}</span>`;
    const flags = p.purpose === "nac"
      ? `CoA ${yn(p.coa)} reauth ${yn(p.reauth)} dACL ${yn(p.dacl)}` : "";
    const findings = p.findings.length
      ? `<ul class="findings">${p.findings.map((f) =>
          `<li><span class="sev ${f.severity} sm">${f.severity}</span> <code>${esc(f.code)}</code> ${esc(f.message)}</li>`).join("")}</ul>`
      : "";
    return `<tr>
      <td class="mono">${esc(p.interface)}${p.endpoint ? `<div class="muted small">→ ${esc(p.endpoint)}</div>` : ""}</td>
      <td>${esc(p.purpose)}</td><td>${auth}</td><td>${esc(vlan || "—")}</td><td class="small">${flags}</td>
      <td><span class="badge ${p.verdict}">${p.verdict}</span></td>
    </tr>${findings ? `<tr class="sub"><td colspan="6">${findings}</td></tr>` : ""}`;
  }).join("");

  const eps = d.endpoints.map((e) => `<tr>
      <td><b>${esc(e.name)}</b><div class="muted small mono">${esc(e.mac)}</div></td>
      <td>${esc(e.kind)}</td><td class="mono">${esc(e.port || "—")}</td>
      <td>${esc(e.auth_method)}${e.identity ? `<div class="muted small">${esc(e.identity)}</div>` : ""}</td>
      <td>${esc(e.expected_vlan ?? "—")}</td><td>${esc(e.expected_sgt || "—")}</td>
    </tr>`).join("");

  const nbs = d.neighbors.map((n) => `<tr>
      <td class="mono">${esc(n.local_port || "—")}</td>
      <td><a href="#" data-dev="${esc(n.name)}">${esc(n.name)}</a>
        <span class="muted small">${esc(ROLE_LABEL[n.role || n.kind] || n.kind)}</span></td>
      <td class="mono">${esc(n.remote_port || "—")}</td>
      <td>${esc(n.link || "")}${n.vlan ? ` · vlan ${esc(n.vlan)}` : ""}</td>
    </tr>`).join("");

  $("#dr-body").innerHTML = `
    <div class="dr-health">${healthBar(d.health)}
      <span class="sev crit">${d.counts.crit}</span><span class="sev warn">${d.counts.warn}</span><span class="sev info">${d.counts.info}</span>
    </div>
    <div class="kvs">
      ${kv("Role", ROLE_LABEL[d.role] || d.role)}${kv("Platform", d.platform)}
      ${kv("Mgmt IP", d.mgmt_ip, true)}${kv("Site", d.site)}${kv("WLC", d.wlc)}
    </div>
    <h4>Access</h4>
    ${sshCmd ? `<div class="cmd"><code>${esc(sshCmd)}</code>${copyBtn(sshCmd)}</div>`
             : `<div class="muted small">no management IP — reachable via its controller${d.wlc ? " (" + esc(d.wlc) + ")" : ""}</div>`}
    ${showCmds.length ? `<details open><summary>Troubleshooting commands</summary>
      ${showCmds.map((c) => `<div class="cmd"><code>${esc(c)}</code>${copyBtn(c)}</div>`).join("")}</details>` : ""}
    ${ports ? `<h4>Switchports (${d.ports.length})</h4><div class="table-scroll"><table class="dt"><thead><tr>
      <th>interface</th><th>purpose</th><th>auth / power</th><th>VLAN</th><th>controls</th><th></th></tr></thead>
      <tbody>${ports}</tbody></table></div>` : ""}
    ${eps ? `<h4>Attached endpoints (${d.endpoints.length})</h4><div class="table-scroll"><table class="dt"><thead><tr>
      <th>endpoint</th><th>kind</th><th>port</th><th>auth</th><th>VLAN</th><th>SGT</th></tr></thead>
      <tbody>${eps}</tbody></table></div>` : ""}
    <h4>Neighbors (${d.neighbors.length})</h4><div class="table-scroll"><table class="dt"><thead><tr>
      <th>local</th><th>neighbor</th><th>remote</th><th>link</th></tr></thead><tbody>${nbs}</tbody></table></div>`;

  $("#drawer").hidden = false;
  $("#scrim").hidden = false;
  focusNode(name);
}

function closeDrawer() { $("#drawer").hidden = true; $("#scrim").hidden = true; }

// ---------------------------------------------------------------- hover detail

// every link touching `id`, as { neighbor, localPort, remotePort, kind, vlan, auth }
function connectionsOf(id) {
  const out = [];
  for (const e of GRAPH.edges) {
    if (e.from !== id && e.to !== id) continue;
    const neighbor = e.from === id ? e.to : e.from;
    const ports = e.ports || {};
    out.push({
      neighbor,
      localPort: ports[id] || null,
      remotePort: ports[neighbor] || null,
      kind: e.kind || "link",
      vlan: e.access_vlan || null,
      auth: e.auth_method || null,
    });
  }
  return out.sort((a, b) => (a.localPort || "z").localeCompare(b.localPort || "z"));
}

function describeNode(n) {
  const bits = [];
  if (n.role) bits.push(n.role);
  if (n.platform && n.platform !== "unknown") bits.push(n.platform);
  if (n.mgmt_ip) bits.push("mgmt " + n.mgmt_ip);
  if (n.site) bits.push(n.site);
  if (n.mac) bits.push(n.mac);
  if (n.security) bits.push(n.security);
  const d = DEVICES[n.id];
  if (d) bits.push(`health ${d.health}`);
  return bits.join("  ·  ");
}

function renderHover(html) { $("#hoverinfo").innerHTML = html; }

function hoverNodeInfo(id) {
  const n = nodeById(id);
  if (!n) return;
  const rows = connectionsOf(id).map((c) => {
    const lp = c.localPort ? `<b>${esc(c.localPort)}</b>` : "<i>—</i>";
    const rp = c.remotePort ? ` <span class="muted">[${esc(c.remotePort)}]</span>` : "";
    const tags = [c.kind, c.vlan ? "vlan " + c.vlan : null, c.auth].filter(Boolean).join(", ");
    return `<tr><td>${lp}</td><td>→ ${esc(c.neighbor)}${rp}</td><td class="muted">${esc(tags)}</td></tr>`;
  }).join("");
  renderHover(
    `<div class="hi-head">${esc(n.id)} <span class="muted">${esc(describeNode(n))}</span></div>` +
    (rows ? `<table class="hi-table"><tbody>${rows}</tbody></table>`
          : `<span class="muted">no links</span>`)
  );
}

function hoverEdgeInfo(edge) {
  const ports = edge.ports || {};
  const a = `${esc(edge.from)}${ports[edge.from] ? " <b>" + esc(ports[edge.from]) + "</b>" : ""}`;
  const b = `${esc(edge.to)}${ports[edge.to] ? " <b>" + esc(ports[edge.to]) + "</b>" : ""}`;
  const tags = [edge.kind, edge.access_vlan ? "vlan " + edge.access_vlan : null, edge.auth_method]
    .filter(Boolean).join(", ");
  renderHover(`<div class="hi-head">${a} &nbsp;⟷&nbsp; ${b}</div><span class="muted">${esc(tags)}</span>`);
}

// ---------------------------------------------------------------- topology

async function loadTopology() {
  const t = await getJSON("/api/topology");
  GRAPH = t.graph;
  $("#topo-name").textContent = t.graph.name;
  $("#node-list").innerHTML = GRAPH.nodes.map((n) => `<option value="${esc(n.id)}">`).join("");
  render2d();
  renderLegend();

  const v = t.validation;
  $("#validation").innerHTML =
    (v.ok ? "✓ topology valid" : `<span class="err">✗ ${v.errors.length} error(s)</span>`) +
    (v.warnings.length ? ` · ${v.warnings.length} warning(s)` : "") +
    [...v.errors.map((x) => `<div class="err">• ${esc(x)}</div>`), ...v.warnings.map((x) => `<div>• ${esc(x)}</div>`)].join("");
}

function renderLegend() {
  let items;
  if (colorBy() === "health") {
    items = [["good ≥90", HEALTH_COLOR.good], ["fair ≥70", HEALTH_COLOR.fair], ["poor", HEALTH_COLOR.poor], ["n/a", HEALTH_COLOR.none]];
  } else {
    const present = new Set(GRAPH.nodes.map((n) => n.role || n.kind));
    items = Object.keys(NODE_COLOR).filter((k) => present.has(k)).map((k) => [ROLE_LABEL[k] || k, NODE_COLOR[k]]);
  }
  $("#legend").innerHTML = items.map(([l, c]) => `<span><i style="background:${c}"></i>${esc(l)}</span>`).join("");
}

function render2d() {
  const fg = getComputedStyle(document.body).color;
  const nodes = GRAPH.nodes.map((n) => ({
    id: n.id,
    label: n.id,
    group: n.role || n.kind,
    shape: n.kind === "endpoint" ? "box" : n.kind === "ssid" ? "hexagon" : "dot",
    color: nodeColor(n),
    font: { color: fg },
    title: `${n.id} — ${describeNode(n) || n.kind}`,
  }));
  const edgeData = GRAPH.edges.map((e, i) => ({
    id: "e" + i, from: e.from, to: e.to, label: e.kind || "", font: { size: 9, color: fg, strokeWidth: 0 },
    color: { color: LINK_COLOR[e.kind] || "#99a", opacity: 0.7 },
    dashes: e.kind === "capwap" || e.kind === "broadcast" || e.kind === "mgmt",
    _raw: e,
    title: [e.ports && e.ports[e.from], "⟷", e.ports && e.ports[e.to]].filter(Boolean).join(" ") ||
           (e.kind || "link"),
  }));

  if (net2d) net2d.destroy();
  net2d = new vis.Network($("#graph"), { nodes, edges: edgeData }, {
    physics: { stabilization: true, barnesHut: { springLength: 130 } },
    edges: { smooth: false },
    nodes: { size: 14 },
    interaction: { hover: true, tooltipDelay: 120 },
  });
  net2d.on("hoverNode", (p) => hoverNodeInfo(p.node));
  net2d.on("hoverEdge", (p) => {
    const ed = edgeData.find((x) => x.id === p.edge);
    if (ed) hoverEdgeInfo(ed._raw);
  });
  net2d.on("click", (p) => {
    if (p.nodes.length) openDevice(p.nodes[0]);
    else if (p.edges.length) {
      const ed = edgeData.find((x) => x.id === p.edges[0]);
      if (ed) hoverEdgeInfo(ed._raw);
    }
  });
}

// ---- 3D

const TIER_GAP = 48;
const GRID_SIZE = 300;
const FLOW_KINDS = new Set(["capwap", "endpoint", "broadcast", "mgmt"]);
const G3 = { endpoints: true, flows: true, rotate: false, timer: null };

function labelSprite(text, color) {
  const c = document.createElement("canvas");
  const ctx = c.getContext("2d");
  const font = "600 28px system-ui, sans-serif";
  ctx.font = font;
  c.width = Math.ceil(ctx.measureText(text).width) + 16;
  c.height = 40;
  ctx.font = font;
  ctx.fillStyle = color;
  ctx.textBaseline = "middle";
  ctx.fillText(text, 8, 20);
  const tex = new THREE.CanvasTexture(c);
  tex.minFilter = THREE.LinearFilter;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthWrite: false, transparent: true }));
  sp.scale.set(c.width / 4, c.height / 4, 1);
  return sp;
}

function nodeSize(n) {
  const d = DEVICES[n.id];
  if (!d) return n.kind === "endpoint" ? 4 : 5;
  return { catalyst_center: 10, ise: 10, core: 12, distribution: 11, wlc: 9, access: 9, ap: 7 }[d.role] || 8;
}

function nodeObject(n) {
  const group = new THREE.Group();
  const color = nodeColor(n);
  const r = nodeSize(n);
  let geo;
  if (n.kind === "endpoint") geo = new THREE.BoxGeometry(r * 1.5, r * 1.5, r * 1.5);
  else if (n.kind === "ssid") geo = new THREE.OctahedronGeometry(r * 1.2);
  else if (["core", "distribution", "access"].includes(n.role)) geo = new THREE.CylinderGeometry(r, r, r * 0.9, 24);
  else geo = new THREE.SphereGeometry(r, 24, 16);
  const mesh = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ color, transparent: true, opacity: 0.95 }));
  group.add(mesh);

  const d = DEVICES[n.id];
  if (d && (d.counts.crit || d.counts.warn)) {
    // halo around devices with open findings
    const halo = new THREE.Mesh(
      new THREE.TorusGeometry(r * 1.6, 0.6, 8, 40),
      new THREE.MeshBasicMaterial({ color: d.counts.crit ? HEALTH_COLOR.poor : HEALTH_COLOR.fair }));
    halo.rotation.x = Math.PI / 2;
    group.add(halo);
  }
  const lbl = labelSprite(n.id, getComputedStyle(document.body).color);
  lbl.position.y = r + 8;
  group.add(lbl);
  return group;
}

function tierPlanes(scene) {
  const planes = new THREE.Group();
  planes.name = "tier-planes";
  const muted = getComputedStyle(document.body).getPropertyValue("--muted").trim() || "#888";
  const tiers = new Set(GRAPH.nodes.filter(visible3d).map(nodeTier));
  for (const t of tiers) {
    const y = (t - 2.5) * TIER_GAP;
    const grid = new THREE.GridHelper(GRID_SIZE, 10, muted, muted);
    grid.material.transparent = true;
    grid.material.opacity = 0.18;
    grid.position.y = y;
    planes.add(grid);
    const lbl = labelSprite(TIER_NAME[t] || `tier ${t}`, muted);
    lbl.position.set(-GRID_SIZE / 2 - 30, y + 4, 0);
    planes.add(lbl);
  }
  const old = scene.getObjectByName("tier-planes");
  if (old) scene.remove(old);
  scene.add(planes);
}

function visible3d(n) { return G3.endpoints || (n.kind !== "endpoint" && n.kind !== "ssid"); }

function graph3dData() {
  const nodes = GRAPH.nodes.filter(visible3d).map((n) => ({ ...n, fy: (nodeTier(n) - 2.5) * TIER_GAP }));
  const ids = new Set(nodes.map((n) => n.id));
  const links = GRAPH.edges.filter((e) => ids.has(e.from) && ids.has(e.to))
    .map((e) => ({ ...e, source: e.from, target: e.to }));
  return { nodes, links };
}

function render3d() {
  if (typeof ForceGraph3D === "undefined" || typeof THREE === "undefined") {
    $("#graph3d").innerHTML = `<div class="g3-fallback">3D view needs the three.js / 3d-force-graph scripts from the CDN — check your connection.</div>`;
    return;
  }
  const box = $("#graph3d");
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  if (!net3d) {
    net3d = ForceGraph3D()(box)
      .backgroundColor(dark ? "#0f1216" : "#f7f9fb")
      .showNavInfo(false)
      .nodeId("id")
      .nodeLabel((n) => `<div class="g3-tip"><b>${esc(n.id)}</b><br>${esc(describeNode(n) || n.kind)}</div>`)
      .nodeThreeObject(nodeObject)
      .linkColor((l) => LINK_COLOR[l.kind] || "#99a")
      .linkOpacity(0.8)
      .linkWidth((l) => (l.kind === "fiber" ? 2.2 : l.kind === "trunk" ? 1.6 : 0.6))
      .linkLabel((l) => {
        const p = l.ports || {};
        const a = l.source.id ?? l.source, b = l.target.id ?? l.target;
        return `<div class="g3-tip">${esc(a)} ${esc(p[a] || "")} ⟷ ${esc(b)} ${esc(p[b] || "")}<br>
          <span>${esc([l.kind, l.access_vlan && "vlan " + l.access_vlan, l.auth_method].filter(Boolean).join(", "))}</span></div>`;
      })
      .linkDirectionalParticles((l) => (G3.flows && FLOW_KINDS.has(l.kind) ? 3 : G3.flows ? 1 : 0))
      .linkDirectionalParticleWidth(2.2)
      .linkDirectionalParticleSpeed((l) => (l.kind === "endpoint" ? 0.006 : 0.004))
      .linkDirectionalParticleColor((l) => LINK_COLOR[l.kind] || "#99a")
      .onNodeHover((n) => { box.style.cursor = n ? "pointer" : ""; if (n) hoverNodeInfo(n.id); })
      .onLinkHover((l) => { if (l) hoverEdgeInfo({ ...l, from: l.source.id, to: l.target.id }); })
      .onNodeClick((n) => openDevice(n.id));
    net3d.d3Force("charge").strength(-260);
    net3d.cameraPosition({ x: 0, y: 140, z: 420 });
    new ResizeObserver(() => net3d.width(box.clientWidth).height(box.clientHeight)).observe(box);
  }
  net3d.graphData(graph3dData());
  tierPlanes(net3d.scene());
  net3d.width(box.clientWidth).height(box.clientHeight);
  setTimeout(() => net3d.zoomToFit(600, 40), 900);
}

function focusNode(id) {
  if (VIEW === "3d" && net3d) {
    const n = net3d.graphData().nodes.find((x) => x.id === id);
    if (!n || n.x == null) return;
    const dist = 160;
    const ratio = 1 + dist / Math.hypot(n.x || 1, n.y || 1, n.z || 1);
    net3d.cameraPosition({ x: n.x * ratio, y: n.y * ratio + 30, z: n.z * ratio }, n, 1200);
  } else if (net2d && nodeById(id)) {
    net2d.selectNodes([id]);
    net2d.focus(id, { scale: 1.2, animation: { duration: 600 } });
  }
}

function setView(v) {
  VIEW = v;
  $$(".seg button").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
  $("#graph").hidden = v !== "2d";
  $("#graph3d").hidden = v !== "3d";
  $("#controls3d").hidden = v !== "3d";
  if (v === "3d") render3d();
  else if (G3.timer) { clearInterval(G3.timer); G3.timer = null; G3.rotate = false; $("#g3-rotate").classList.remove("on"); }
  try { localStorage.setItem("netsim.view", v); } catch {}
}

function toggleRotate() {
  G3.rotate = !G3.rotate;
  $("#g3-rotate").classList.toggle("on", G3.rotate);
  if (G3.timer) { clearInterval(G3.timer); G3.timer = null; }
  if (!G3.rotate || !net3d) return;
  let angle = 0;
  const p = net3d.cameraPosition();
  const dist = Math.hypot(p.x, p.z) || 400;
  G3.timer = setInterval(() => {
    angle += Math.PI / 600;
    net3d.cameraPosition({ x: dist * Math.sin(angle), z: dist * Math.cos(angle) });
  }, 16);
}

function recolor() {
  renderLegend();
  if (net2d) render2d();
  if (net3d) net3d.nodeThreeObject(nodeObject);
}

// ---------------------------------------------------------------- scenarios

async function loadScenarios() {
  const list = await getJSON("/api/scenarios");
  const ul = $("#scenarios");
  ul.innerHTML = "";
  for (const s of list) {
    const li = el("li");
    const left = el("div");
    left.innerHTML = `<div><b>${esc(s.title)}</b></div>
      <div class="meta">${esc(s.description)}<br>requires: ${esc(s.requires.join(", ") || "—")} ·
      snapshot: ${s.has_snapshot ? "yes" : "none"}</div>`;
    const btn = el("button");
    btn.textContent = "run";
    btn.onclick = () => runScenario(s.name, s.title, btn);
    li.append(left, btn);
    ul.append(li);
  }
}

function stepCard(step) {
  const c = el("div", "step");
  const b = el("div", "badge " + step.verdict);
  b.textContent = step.verdict;
  const body = el("div");
  body.append(Object.assign(el("div", "name"), { textContent: step.name }));
  if (step.request) body.append(Object.assign(el("div", "req"), { textContent: step.request }));
  if (step.summary) body.append(Object.assign(el("div", "sum"), { textContent: step.summary }));
  if (step.notes && step.notes.length) {
    const ul = el("ul");
    step.notes.forEach((n) => ul.append(Object.assign(el("li"), { textContent: n })));
    body.append(ul);
  }
  if (step.data) {
    const d = el("details");
    d.append(Object.assign(el("summary"), { textContent: "data" }));
    const pre = el("pre");
    pre.textContent = JSON.stringify(step.data, null, 2);
    d.append(pre);
    body.append(d);
  }
  c.append(b, body);
  return c;
}

function runScenario(name, title, btn) {
  const box = $("#runbox");
  box.hidden = false;
  $("#run-title").textContent = title;
  $("#run-status").textContent = "running…";
  $("#steps").innerHTML = "";
  $("#comparison").textContent = "";
  btn.disabled = true;

  const mode = $("#mode").value;
  const es = new EventSource(`/api/scenario/${name}/stream?mode=${mode}`);
  es.addEventListener("step", (e) => {
    $("#steps").append(stepCard(JSON.parse(e.data)));
    $("#steps").scrollTop = $("#steps").scrollHeight;
  });
  es.addEventListener("result", (e) => {
    const r = JSON.parse(e.data);
    const c = r.counts;
    $("#run-status").textContent = `${c.pass} pass · ${c.fail} fail · ${c.warn} warn · ${c.info} info`;
  });
  es.addEventListener("comparison", (e) => {
    const cmp = JSON.parse(e.data);
    const box = $("#comparison");
    box.className = "comparison " + (cmp.status === "match" ? "match" : cmp.status === "no-baseline" ? "" : "drift");
    let html = `<b>Expected vs actual:</b> ${esc(cmp.status)}`;
    const vd = cmp.verdict_diff || {};
    if (Object.keys(vd).length) {
      html += "<ul>" + Object.entries(vd).map(([k, d]) =>
        `<li>${esc(k)}: expected <b>${esc(d.expected)}</b>, actual <b>${esc(d.actual)}</b></li>`).join("") + "</ul>";
    }
    box.innerHTML = html;
  });
  es.addEventListener("error", (e) => {
    if (e.data) { try { $("#run-status").textContent = "error: " + JSON.parse(e.data).message; } catch {} }
  });
  es.addEventListener("done", () => { es.close(); btn.disabled = false; loadRuns(); loadQuality(); });
}

async function loadRuns() {
  const rows = await getJSON("/api/runs");
  const tb = $("#runs tbody");
  tb.innerHTML = rows.map((r) => {
    const c = r.counts || {};
    const st = r.comparison_status ?? "";
    const cls = st === "match" ? "pass" : st === "no-baseline" || !st ? "" : "warn";
    return `<tr><td class="mono small">${esc(r.run_id)}</td><td>${esc(r.scenario)}</td><td>${esc(r.mode)}</td>
      <td>${c.pass ?? ""}</td><td>${c.fail ?? ""}</td><td>${c.warn ?? ""}</td>
      <td>${st ? `<span class="badge ${cls}">${esc(st)}</span>` : ""}</td></tr>`;
  }).join("") || `<tr><td colspan="7" class="muted">no runs yet — run a scenario above</td></tr>`;
}

// ---------------------------------------------------------------- wiring

document.addEventListener("click", (e) => {
  const link = e.target.closest("[data-dev]");
  if (link) { e.preventDefault(); openDevice(link.dataset.dev); return; }
  const cp = e.target.closest("[data-copy]");
  if (cp) {
    navigator.clipboard?.writeText(cp.dataset.copy).then(() => {
      cp.textContent = "copied"; setTimeout(() => (cp.textContent = "copy"), 1200);
    });
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeDrawer();
  if (e.key === "Enter" && e.target.matches("tr[data-dev]")) openDevice(e.target.dataset.dev);
});
$("#dr-close").onclick = closeDrawer;
$("#scrim").onclick = closeDrawer;
$("#dev-filter").oninput = renderDevices;
$("#dev-role").onchange = renderDevices;
$$("#devices th[data-sort]").forEach((th) => (th.onclick = () => {
  DEV_SORT.dir = DEV_SORT.key === th.dataset.sort ? -DEV_SORT.dir : 1;
  DEV_SORT.key = th.dataset.sort;
  renderDevices();
}));
$$(".seg button").forEach((b) => (b.onclick = () => setView(b.dataset.view)));
$("#color-by").onchange = recolor;
$("#node-search").onchange = (e) => {
  const id = e.target.value.trim();
  if (nodeById(id)) { focusNode(id); hoverNodeInfo(id); }
};
$("#g3-reset").onclick = () => net3d && net3d.zoomToFit(600, 40);
$("#g3-rotate").onclick = toggleRotate;
$("#g3-endpoints").onclick = (e) => {
  G3.endpoints = !G3.endpoints; e.target.classList.toggle("on", G3.endpoints); render3d();
};
$("#g3-flow").onclick = (e) => {
  G3.flows = !G3.flows; e.target.classList.toggle("on", G3.flows);
  if (net3d) net3d.linkDirectionalParticles(net3d.linkDirectionalParticles());
};
$("#refresh-runs").onclick = () => { loadRuns(); loadQuality(); };

(async () => {
  loadEnv(); loadScenarios(); loadRuns(); loadQuality();
  await loadDevices();       // inventory first so graph nodes can be colored by health
  await loadTopology();
  let saved = null;
  try { saved = localStorage.getItem("netsim.view"); } catch {}
  if (saved === "3d") setView("3d");
})();
