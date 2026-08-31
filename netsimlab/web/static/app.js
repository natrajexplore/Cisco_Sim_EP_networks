const $ = (s) => document.querySelector(s);
const el = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };

const NODE_COLOR = {
  catalyst_center: "#6f42c1", ise: "#d63384", core: "#0b5cad", distribution: "#1f7a8c",
  access: "#2a9d8f", wlc: "#e76f51", ap: "#f4a261", firewall: "#c1121f",
  ssid: "#8d99ae", endpoint: "#adb5bd",
};

async function loadEnv() {
  const s = await (await fetch("/api/settings")).json();
  $("#env").textContent = `mode=${s.mode} · dnac=${s.dnac_base_url} · ise=${s.ise_base_url}`;
  $("#mode").value = s.mode;
}

async function loadTopology() {
  const t = await (await fetch("/api/topology")).json();
  $("#topo-name").textContent = t.graph.name;
  const nodes = t.graph.nodes.map((n) => ({
    id: n.id,
    label: n.id,
    group: n.role || n.kind,
    shape: n.kind === "endpoint" ? "box" : n.kind === "ssid" ? "hexagon" : "dot",
    color: NODE_COLOR[n.role] || NODE_COLOR[n.kind] || "#888",
    font: { color: getComputedStyle(document.body).color },
  }));
  const edges = t.graph.edges.map((e) => ({ from: e.from, to: e.to, label: e.kind || "", font: { size: 9 } }));
  new vis.Network($("#graph"), { nodes, edges }, {
    physics: { stabilization: true, barnesHut: { springLength: 130 } },
    edges: { color: { color: "#99a", opacity: 0.6 }, smooth: false },
    nodes: { size: 14 },
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
