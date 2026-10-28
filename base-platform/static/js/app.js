const state = {
  token: localStorage.getItem("base_token") || "",
  tenantId: localStorage.getItem("base_tenant") || "",
  user: null,
  repoId: localStorage.getItem("base_repo") || "",
};

let navRef = null;

function setAuthed(ok) {
  const gate = document.getElementById("auth-gate");
  const content = document.getElementById("app-content");
  if (gate) gate.classList.toggle("is-hidden", ok);
  if (content) content.classList.toggle("is-hidden", !ok);
  if (navRef?.setAuthButtons) navRef.setAuthButtons(ok);
  if (!ok) {
    document.getElementById("session-info").textContent = "未登录";
    const agentSelect = document.getElementById("agent-id");
    if (agentSelect) agentSelect.innerHTML = `<option value="">请先登录后加载</option>`;
  }
}

function logout() {
  state.token = "";
  state.user = null;
  state.tenantId = "";
  localStorage.removeItem("base_token");
  localStorage.removeItem("base_tenant");
  setAuthed(false);
  BaseUI.toast("已退出登录");
  openAppLogin();
}

function openAppLogin() {
  BaseUI.openLoginModal({
    requireAuth: true,
    onSubmit: doLogin,
  });
}

async function api(path, { method = "GET", body, formData } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (state.tenantId) headers["X-Tenant-Id"] = state.tenantId;
  let payload;
  if (formData) {
    payload = formData;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const resp = await fetch(`/api/v1${path}`, { method, headers, body: payload });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || (data.code && data.code !== "OK")) {
    throw new Error(data.message || `HTTP ${resp.status}`);
  }
  return data.data;
}

function show(elId, obj) {
  document.getElementById(elId).textContent =
    typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
}

async function refreshUser() {
  if (!state.token) return;
  try {
    state.user = await api("/auth/user-info");
    document.getElementById("session-info").textContent =
      `${state.user.username} @ ${state.user.tenant_id || state.tenantId}`;
  } catch (e) {
    BaseUI.toast("登录态失效，请重新登录");
    state.token = "";
    state.user = null;
    localStorage.removeItem("base_token");
    setAuthed(false);
    throw e;
  }
}

async function loadAgents() {
  const select = document.getElementById("agent-id");
  const hint = document.getElementById("agent-hint");
  if (!select) return;
  const list = await api("/quota/agents");
  if (!list.length) {
    select.innerHTML = `<option value="">本租户尚未登记智能体</option>`;
    if (hint) {
      hint.textContent = "请让平台管理员在管理后台为该租户配置智能体配额后再调用。";
    }
    return;
  }
  select.innerHTML = list
    .map(
      (a) =>
        `<option value="${a.agent_id}">${a.agent_id}（剩余 ${a.remain_value}/${a.limit_value}）</option>`
    )
    .join("");
  if (hint) {
    hint.textContent = `当前租户共 ${list.length} 个已登记智能体，跨租户或未登记 ID 不可调用。`;
  }
}

async function doLogin(form) {
  const data = await api("/auth/login", { method: "POST", body: form });
  state.token = data.access_token;
  state.tenantId = data.tenant_id || "";
  localStorage.setItem("base_token", state.token);
  if (state.tenantId) localStorage.setItem("base_tenant", state.tenantId);
  await refreshUser();
  setAuthed(true);
  BaseUI.toast("登录成功");
  await loadAgents().catch((e) => BaseUI.toast(e.message));
  await loadStats().catch(() => {});
  await loadQuota().catch(() => {});
}

async function requireLogin() {
  if (!state.token) {
    openAppLogin();
    throw new Error("请先登录");
  }
}

async function chatOnce() {
  await requireLogin();
  const content = document.getElementById("chat-input").value.trim();
  const agent_id = document.getElementById("agent-id").value.trim();
  if (!content) return BaseUI.toast("请输入问题");
  if (!agent_id) return BaseUI.toast("请选择本租户已登记的智能体");
  const data = await api("/gateway/chat/completions", {
    method: "POST",
    body: {
      agent_id,
      model: "mock-gpt",
      stream: false,
      messages: [{ role: "user", content }],
    },
  });
  show("chat-out", data);
  await loadAgents().catch(() => {});
  await loadStats();
  await loadQuota();
}

async function createKb() {
  await requireLogin();
  const repo_name = document.getElementById("kb-name").value.trim() || "演示知识库";
  const data = await api("/kb/repo/create", { method: "POST", body: { repo_name } });
  state.repoId = data.repo_id;
  localStorage.setItem("base_repo", state.repoId);
  show("kb-out", data);
  BaseUI.toast("知识库已创建");
}

async function uploadDoc() {
  await requireLogin();
  if (!state.repoId) return BaseUI.toast("请先创建知识库");
  const text = document.getElementById("kb-text").value.trim();
  if (!text) return BaseUI.toast("请填写文档内容");
  const blob = new Blob([text], { type: "text/plain" });
  const fd = new FormData();
  fd.append("repo_id", state.repoId);
  fd.append("tags", "demo");
  fd.append("file", blob, "demo.txt");
  const data = await api("/kb/repo/document/upload", { method: "POST", formData: fd });
  show("kb-out", data);
  BaseUI.toast("文档已入库");
}

async function searchKb() {
  await requireLogin();
  if (!state.repoId) return BaseUI.toast("请先创建知识库");
  const query = document.getElementById("kb-query").value.trim() || "基座";
  const data = await api("/kb/repo/search", {
    method: "POST",
    body: { repo_id: state.repoId, query, top_n: 5 },
  });
  show("kb-out", data);
}

async function loadQuota() {
  await requireLogin();
  const agent_id = document.getElementById("agent-id").value.trim();
  if (!agent_id) {
    show("quota-out", { message: "请先选择已登记智能体" });
    return;
  }
  const data = await api(`/quota/get?agent_id=${encodeURIComponent(agent_id)}`);
  show("quota-out", data);
}

async function loadStats() {
  if (!state.token) return;
  const data = await api("/gateway/call-stat");
  show("stat-out", data);
}

async function loadLogs() {
  await requireLogin();
  const data = await api("/log/model-call/list?page=1&page_size=10");
  show("log-out", data);
}

window.addEventListener("DOMContentLoaded", async () => {
  navRef = BaseUI.mountNav({
    onLogin: () => openAppLogin(),
    onLogout: () => logout(),
    onProfile: () => {
      if (!state.user) {
        openAppLogin();
        return;
      }
      BaseUI.openProfile({ user: state.user || { tenant_id: state.tenantId } });
    },
    onDisclaimer: () =>
      BaseUI.openDisclaimer({
        content:
          "【教育样板】本智能体提供的学习辅导仅供参考，不构成专业教学结论。文案由子平台传入，基座仅提供弹窗框架。",
      }),
  });
  setAuthed(false);

  document.getElementById("btn-gate-login").onclick = () => openAppLogin();
  document.getElementById("btn-chat").onclick = () =>
    chatOnce().catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-kb-create").onclick = () =>
    createKb().catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-kb-upload").onclick = () =>
    uploadDoc().catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-kb-search").onclick = () =>
    searchKb().catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-quota").onclick = () =>
    loadQuota().catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-logs").onclick = () =>
    loadLogs().catch((e) => BaseUI.toast(e.message));

  try {
    if (!state.token) {
      openAppLogin();
    } else {
      await refreshUser();
      setAuthed(true);
      await loadAgents().catch((e) => BaseUI.toast(e.message));
      await loadStats().catch(() => {});
      await loadQuota().catch(() => {});
    }
  } catch (e) {
    setAuthed(false);
    openAppLogin();
  }
});
