const state = {
  token: localStorage.getItem("base_token") || "",
  tenantId: localStorage.getItem("base_tenant") || "",
  nodes: [],
  edges: [],
  selected: null,
  linkFrom: null,
};

async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (state.tenantId) headers["X-Tenant-Id"] = state.tenantId;
  const resp = await fetch(`/api/v1${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || (data.code && data.code !== "OK")) throw new Error(data.message || `HTTP ${resp.status}`);
  return data.data;
}

function uid(prefix) {
  return `${prefix}_${Math.random().toString(16).slice(2, 8)}`;
}

function addNode(type) {
  const id = uid(type[0] || "n");
  const defaults = {
    retrieve: { top_n: 3, repo_id: "" },
    prompt: { content: "请回答：{query}" },
    llm: { model_id: "mock-gpt", prompt: "基于上下文回答。\n问题：{query}\n资料：{context}", context_from: "" },
    plugin: { plugin_id: "", params: {} },
  };
  state.nodes.push({
    id,
    type,
    x: 80 + state.nodes.length * 40,
    y: 80 + state.nodes.length * 30,
    data: defaults[type] || {},
  });
  render();
}

function buildDsl() {
  // 按边拓扑排序近似：无入边的先，否则按创建顺序
  const indeg = Object.fromEntries(state.nodes.map((n) => [n.id, 0]));
  state.edges.forEach((e) => {
    if (indeg[e.to] != null) indeg[e.to] += 1;
  });
  const ordered = [...state.nodes].sort((a, b) => indeg[a.id] - indeg[b.id]);
  const steps = ordered.map((n) => {
    const step = { id: n.id, type: n.type, ...n.data };
    const incoming = state.edges.find((e) => e.to === n.id);
    if (n.type === "llm" && incoming) step.context_from = incoming.from;
    return step;
  });
  return { steps };
}

function renderProps(node) {
  const box = document.getElementById("props");
  if (!node) {
    box.innerHTML = `<p class="muted">选中画布中的节点进行编辑</p>`;
    return;
  }
  const fields = Object.keys(node.data)
    .map((k) => {
      const val = typeof node.data[k] === "object" ? JSON.stringify(node.data[k]) : node.data[k];
      return `<label>${k}</label><input data-k="${k}" value='${String(val).replace(/'/g, "&#39;")}' />`;
    })
    .join("");
  box.innerHTML = `
    <p><b>${node.id}</b> · ${node.type}</p>
    ${fields}
    <div class="row" style="margin-top:10px">
      <button class="base-btn" id="btn-del-node">删除节点</button>
    </div>
  `;
  box.querySelectorAll("input[data-k]").forEach((input) => {
    input.onchange = () => {
      const k = input.dataset.k;
      let v = input.value;
      try {
        if (v.trim().startsWith("{") || v.trim().startsWith("[")) v = JSON.parse(v);
        else if (!Number.isNaN(Number(v)) && v.trim() !== "") v = Number(v);
      } catch {}
      node.data[k] = v;
      refreshDsl();
    };
  });
  document.getElementById("btn-del-node").onclick = () => {
    state.nodes = state.nodes.filter((n) => n.id !== node.id);
    state.edges = state.edges.filter((e) => e.from !== node.id && e.to !== node.id);
    state.selected = null;
    render();
  };
}

function refreshDsl() {
  document.getElementById("dsl-out").textContent = JSON.stringify(buildDsl(), null, 2);
}

function drawEdges() {
  const svg = document.getElementById("edges");
  svg.innerHTML = "";
  state.edges.forEach((e) => {
    const a = state.nodes.find((n) => n.id === e.from);
    const b = state.nodes.find((n) => n.id === e.to);
    if (!a || !b) return;
    const x1 = a.x + 180;
    const y1 = a.y + 36;
    const x2 = b.x;
    const y2 = b.y + 36;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const mx = (x1 + x2) / 2;
    path.setAttribute("d", `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`);
    path.setAttribute("stroke", "#d4a017");
    path.setAttribute("stroke-width", "2");
    path.setAttribute("fill", "none");
    svg.appendChild(path);
  });
}

function render() {
  const canvas = document.getElementById("canvas");
  canvas.innerHTML = "";
  state.nodes.forEach((node) => {
    const el = document.createElement("div");
    el.className = "wf-node" + (state.selected === node.id ? " active" : "");
    el.style.left = node.x + "px";
    el.style.top = node.y + "px";
    el.innerHTML = `
      <div class="port in" data-port="in"></div>
      <h4>${node.id}</h4>
      <div class="type">${node.type}</div>
      <div class="port out" data-port="out"></div>
    `;
    el.onmousedown = (ev) => {
      if (ev.target.dataset.port) return;
      state.selected = node.id;
      renderProps(node);
      const sx = ev.clientX;
      const sy = ev.clientY;
      const ox = node.x;
      const oy = node.y;
      const move = (e2) => {
        node.x = ox + e2.clientX - sx;
        node.y = oy + e2.clientY - sy;
        el.style.left = node.x + "px";
        el.style.top = node.y + "px";
        drawEdges();
      };
      const up = () => {
        window.removeEventListener("mousemove", move);
        window.removeEventListener("mouseup", up);
        render();
      };
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", up);
    };
    el.querySelector('[data-port="out"]').onmousedown = (ev) => {
      ev.stopPropagation();
      state.linkFrom = node.id;
      BaseUI.toast(`已选择起点 ${node.id}，请点目标入端口`);
    };
    el.querySelector('[data-port="in"]').onmousedown = (ev) => {
      ev.stopPropagation();
      if (!state.linkFrom || state.linkFrom === node.id) return;
      if (!state.edges.find((e) => e.from === state.linkFrom && e.to === node.id)) {
        state.edges.push({ from: state.linkFrom, to: node.id });
      }
      state.linkFrom = null;
      render();
    };
    canvas.appendChild(el);
  });
  drawEdges();
  refreshDsl();
  if (state.selected) {
    const n = state.nodes.find((x) => x.id === state.selected);
    if (n) renderProps(n);
  }
}

async function ensureLogin() {
  if (state.token) {
    try {
      const u = await api("/auth/user-info");
      document.getElementById("session-info").textContent = `${u.username} @ ${u.tenant_id || state.tenantId}`;
      return;
    } catch {}
  }
  await new Promise((resolve) => {
    BaseUI.openLoginModal({
      requireAuth: true,
      onSubmit: async (form) => {
        const data = await api("/auth/login", { method: "POST", body: form });
        state.token = data.access_token;
        state.tenantId = data.tenant_id || "";
        localStorage.setItem("base_token", state.token);
        if (state.tenantId) localStorage.setItem("base_tenant", state.tenantId);
        document.getElementById("session-info").textContent = `${data.username} @ ${state.tenantId}`;
        resolve();
      },
    });
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  document.querySelectorAll("[data-type]").forEach((btn) => {
    btn.onclick = () => addNode(btn.dataset.type);
  });
  document.getElementById("btn-save").onclick = async () => {
    try {
      const dsl = buildDsl();
      const data = await api("/workflow/save", {
        method: "POST",
        body: { name: document.getElementById("wf-name").value.trim() || "未命名工作流", dsl },
      });
      BaseUI.toast(`已保存 ${data.wf_id}`);
    } catch (e) {
      BaseUI.toast(e.message);
    }
  };
  document.getElementById("btn-run").onclick = async () => {
    try {
      const dsl = buildDsl();
      const data = await api("/workflow/run", {
        method: "POST",
        body: {
          name: document.getElementById("wf-name").value.trim() || "试运行",
          dsl,
          input: { query: "请介绍文化基座", repo_id: "" },
        },
      });
      document.getElementById("dsl-out").textContent = JSON.stringify(data, null, 2);
      BaseUI.toast("试运行完成");
    } catch (e) {
      BaseUI.toast(e.message);
    }
  };
  await ensureLogin();
  addNode("retrieve");
  addNode("llm");
  state.edges.push({ from: state.nodes[0].id, to: state.nodes[1].id });
  render();
});
