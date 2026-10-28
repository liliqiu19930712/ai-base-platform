const state = {
  token: localStorage.getItem("base_token") || "",
  tenantId: localStorage.getItem("base_tenant") || "",
  user: null,
};

async function api(path, { method = "GET", body, formData } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (state.tenantId) headers["X-Tenant-Id"] = state.tenantId;
  let payload;
  if (formData) payload = formData;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const resp = await fetch(`/api/v1${path}`, { method, headers, body: payload });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || (data.code && data.code !== "OK")) throw new Error(data.message || `HTTP ${resp.status}`);
  return data.data;
}

function show(id, obj) {
  document.getElementById(id).textContent =
    typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
}

function setSession() {
  document.getElementById("session-info").textContent = state.user
    ? `${state.user.username} @ ${state.user.tenant_id || state.tenantId}`
    : "未登录";
}

async function afterLogin(data) {
  state.token = data.access_token;
  state.tenantId = data.tenant_id || state.tenantId || "";
  localStorage.setItem("base_token", state.token);
  if (state.tenantId) localStorage.setItem("base_tenant", state.tenantId);
  state.user = await api("/auth/user-info");
  setSession();
  await loadAgents();
  BaseUI.toast("子平台登录成功");
}

async function loadAgents() {
  const list = await api("/agent/list");
  const select = document.getElementById("agent-id");
  select.innerHTML = (list || [])
    .map((a) => `<option value="${a.agent_id}">${a.agent_name || a.agent_id}</option>`)
    .join("") || `<option value="">暂无智能体</option>`;
}

function openLogin() {
  BaseUI.openLoginModal({
    requireAuth: true,
    onSubmit: async (form) => {
      const data = await api("/auth/login", { method: "POST", body: form });
      await afterLogin(data);
    },
  });
}

async function ssoEnter() {
  if (!state.token) return openLogin();
  const ticket = await api("/auth/sso/ticket", {
    method: "POST",
    body: { redirect_uri: location.href, tenant_id: state.tenantId },
  });
  const exchanged = await api("/auth/sso/exchange", {
    method: "POST",
    body: { ticket: ticket.ticket },
  });
  show("sso-out", { issued: ticket, exchanged });
  await afterLogin(exchanged);
}

async function wecomSso() {
  const auth = await api(
    `/auth/sso/wecom/authorize?redirect_uri=${encodeURIComponent(location.href)}&state=culture`
  );
  show("sso-out", auth);
  if (auth.mode === "mock") {
    const data = await api(
      `/auth/sso/wecom/mock-callback?code=culture_user&tenant_id=${encodeURIComponent(state.tenantId || "")}`
    );
    await afterLogin(data);
  } else {
    location.href = auth.authorize_url;
  }
}

window.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("btn-login").onclick = openLogin;
  document.getElementById("btn-logout").onclick = () => {
    state.token = "";
    state.tenantId = "";
    state.user = null;
    localStorage.removeItem("base_token");
    localStorage.removeItem("base_tenant");
    setSession();
    BaseUI.toast("已退出");
  };
  document.getElementById("btn-sso").onclick = () => ssoEnter().catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-wecom").onclick = () => wecomSso().catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-disclaimer").onclick = async () => {
    try {
      const cfg = await api("/compliance/config");
      BaseUI.openDisclaimer({ title: cfg.title, content: cfg.content });
    } catch {
      BaseUI.openDisclaimer({ content: "文化内容仅供参考，不构成专业意见。" });
    }
  };

  document.getElementById("btn-ask").onclick = async () => {
    try {
      const data = await api("/gateway/chat/completions", {
        method: "POST",
        body: {
          agent_id: document.getElementById("agent-id").value,
          messages: [{ role: "user", content: document.getElementById("ask").value }],
        },
      });
      show("ask-out", data);
    } catch (e) {
      BaseUI.toast(e.message);
    }
  };

  document.getElementById("btn-create-kb").onclick = async () => {
    try {
      const data = await api("/kb/repo/create", {
        method: "POST",
        body: { repo_name: "文化典籍库" },
      });
      document.getElementById("repo-id").value = data.repo_id;
      show("kb-out", data);
    } catch (e) {
      BaseUI.toast(e.message);
    }
  };

  document.getElementById("btn-upload-kb").onclick = async () => {
    try {
      const repo_id = document.getElementById("repo-id").value.trim();
      if (!repo_id) throw new Error("请先创建知识库");
      const text =
        "昆曲是中国最古老的剧种之一，以水磨调著称。京剧形成于清代，融合徽汉等声腔，唱念做打完备。非遗保护强调活态传承与当代传播。";
      const fd = new FormData();
      fd.append("repo_id", repo_id);
      fd.append("tags", "heritage");
      fd.append("file", new Blob([text], { type: "text/plain" }), "heritage.txt");
      const data = await api("/kb/repo/document/upload", { method: "POST", formData: fd });
      show("kb-out", data);
    } catch (e) {
      BaseUI.toast(e.message);
    }
  };

  document.getElementById("btn-search").onclick = async () => {
    try {
      const data = await api("/kb/repo/search", {
        method: "POST",
        body: {
          repo_id: document.getElementById("repo-id").value.trim(),
          query: document.getElementById("query").value.trim(),
          top_n: 5,
        },
      });
      show("kb-out", data);
    } catch (e) {
      BaseUI.toast(e.message);
    }
  };

  // URL ticket 自动兑换：?sso_ticket=xxx
  const params = new URLSearchParams(location.search);
  const ticket = params.get("sso_ticket");
  try {
    if (ticket) {
      const data = await api("/auth/sso/exchange", { method: "POST", body: { ticket } });
      await afterLogin(data);
      history.replaceState({}, "", location.pathname);
    } else if (state.token) {
      state.user = await api("/auth/user-info");
      setSession();
      await loadAgents();
    } else {
      setSession();
      openLogin();
    }
  } catch (e) {
    setSession();
    BaseUI.toast(e.message);
    openLogin();
  }
});
