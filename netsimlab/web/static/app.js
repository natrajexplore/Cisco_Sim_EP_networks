const $ = (s) => document.querySelector(s);
const el = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };

const NODE_COLOR = {
  catalyst_center: "#6f42c1", ise: "#d63384", core: "#0b5cad", distribution: "#1f7a8c",
  access: "#2a9d8f", wlc: "#e76f51", ap: "#f4a261", firewall: "#c1121f",
  ssid: "#8d99ae", endpoint: "#adb5bd",
};

async function loadEnv() {
  const s = await (await fetch("/api/settings")).json();
  $("#env").textContent =
    `mode=${s.mode} · dnac=${s.dnac_base_url} · ise=${s.ise_base_url}` +
    (s.wlc_enabled ? ` · wlc=${s.wlc_base_url}` : "");
  $("#mode").value = s.mode;
}

let GRAPH = { nodes: [], edges: [] };

function nodeById(id) { return GRAPH.nodes.find((n) => n.id === id); }

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
  return bits.join("  ·  ");
}

function renderHover(html) { $("#hoverinfo").innerHTML = html; }

function hoverNodeInfo(id) {
  const n = nodeById(id);
  if (!n) return;
  const rows = connectionsOf(id).map((c) => {
    const lp = c.localPort ? `<b>${c.localPort}</b>` : "<i>—</i>";
    const rp = c.remotePort ? ` <span class="muted">[${c.remotePort}]</span>` : "";
    const tags = [c.kind, c.vlan ? "vlan " + c.vlan : null, c.auth].filter(Boolean).join(", ");
    return `<tr><td>${lp}</td><td>→ ${c.neighbor}${rp}</td><td class="muted">${tags}</td></tr>`;
  }).join("");
  renderHover(
    `<div class="hi-head">${n.id} <span class="muted">${describeNode(n)}</span></div>` +
    (rows ? `<table class="hi-table"><tbody>${rows}</tbody></table>`
          : `<span class="muted">no links</span>`)
  );
}

function hoverEdgeInfo(edge) {
  const ports = edge.ports || {};
  const a = `${edge.from}${ports[edge.from] ? " <b>" + ports[edge.from] + "</b>" : ""}`;
  const b = `${edge.to}${ports[edge.to] ? " <b>" + ports[edge.to] + "</b>" : ""}`;
  const tags = [edge.kind, edge.access_vlan ? "vlan " + edge.access_vlan : null, edge.auth_method]
    .filter(Boolean).join(", ");
  renderHover(`<div class="hi-head">${a} &nbsp;⟷&nbsp; ${b}</div><span class="muted">${tags}</span>`);
}

async function loadTopology() {
  const t = await (await fetch("/api/topology")).json();
  GRAPH = t.graph;
  $("#topo-name").textContent = t.graph.name;
  const fg = getComputedStyle(document.body).color;

  const nodes = t.graph.nodes.map((n) => ({
    id: n.id,
    label: n.id,
    group: n.role || n.kind,
    shape: n.kind === "endpoint" ? "box" : n.kind === "ssid" ? "hexagon" : "dot",
    color: NODE_COLOR[n.role] || NODE_COLOR[n.kind] || "#888",
    font: { color: fg },
    title: `${n.id} — ${describeNode(n) || n.kind}`,
  }));
  const edgeData = t.graph.edges.map((e, i) => ({
    id: "e" + i, from: e.from, to: e.to, label: e.kind || "", font: { size: 9 },
    _raw: e,
    title: [e.ports && e.ports[e.from], "⟷", e.ports && e.ports[e.to]].filter(Boolean).join(" ") ||
           (e.kind || "link"),
  }));

  const net = new vis.Network($("#graph"), { nodes, edges: edgeData }, {
    physics: { stabilization: true, barnesHut: { springLength: 130 } },
    edges: { color: { color: "#99a", opacity: 0.6 }, smooth: false },
    nodes: { size: 14 },
    interaction: { hover: true, tooltipDelay: 120 },
  });
  net.on("hoverNode", (p) => hoverNodeInfo(p.node));
  net.on("hoverEdge", (p) => {
    const ed = edgeData.find((x) => x.id === p.edge);
    if (ed) hoverEdgeInfo(ed._raw);
  });
  net.on("click", (p) => {
    if (p.nodes.length) hoverNodeInfo(p.nodes[0]);
    else if (p.edges.length) {
      const ed = edgeData.find((x) => x.id === p.edges[0]);
      if (ed) hoverEdgeInfo(ed._raw);
    }
  });

  const v = t.validation;
  $("#validation").innerHTML =
    (v.ok ? "✓ topology valid" : `<span class="err">✗ ${v.errors.length} error(s)</span>`) +
    (v.warnings.length ? ` · ${v.warnings.length} warning(s)` : "") +
    [...v.errors.map((x) => `<div class="err">• ${x}</div>`), ...v.warnings.map((x) => `<div>• ${x}</div>`)].join("");
}

async function loadScenarios() {
  const list = await (await fetch("/api/scenarios")).json();
  const ul = $("#scenarios");
  ul.innerHTML = "";
  for (const s of list) {
    const li = el("li");
    const left = el("div");
    left.innerHTML = `<div><b>${s.title}</b></div>
      <div class="meta">${s.description}<br>requires: ${s.requires.join(", ") || "—"} ·
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
    d.append(el("summary")).textContent = "data";
    d.querySelector("summary").textContent = "data";
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
    let html = `<b>Expected vs actual:</b> ${cmp.status}`;
    const vd = cmp.verdict_diff || {};
    if (Object.keys(vd).length) {
      html += "<ul>" + Object.entries(vd).map(([k, d]) => `<li>${k}: expected <b>${d.expected}</b>, actual <b>${d.actual}</b></li>`).join("") + "</ul>";
    }
    box.innerHTML = html;
  });
  es.addEventListener("error", (e) => {
    if (e.data) { try { $("#run-status").textContent = "error: " + JSON.parse(e.data).message; } catch {} }
  });
  es.addEventListener("done", () => { es.close(); btn.disabled = false; loadRuns(); });
}

async function loadRuns() {
  const rows = await (await fetch("/api/runs")).json();
  const tb = $("#runs tbody");
  tb.innerHTML = "";
  for (const r of rows) {
    const tr = el("tr");
    const c = r.counts || {};
    tr.innerHTML = `<td>${r.run_id}</td><td>${r.scenario}</td><td>${r.mode}</td>
      <td>${c.pass ?? ""}</td><td>${c.fail ?? ""}</td><td>${c.warn ?? ""}</td><td>${r.comparison_status ?? ""}</td>`;
    tb.append(tr);
  }
}

$("#refresh-runs").onclick = loadRuns;
loadEnv(); loadTopology(); loadScenarios(); loadRuns();
