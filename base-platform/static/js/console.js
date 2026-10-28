const state = {
  token: localStorage.getItem("base_token") || "",
  tenantId: localStorage.getItem("base_tenant") || "",
  user: null,
};

let navRef = null;

function setAuthed(ok) {
  document.getElementById("auth-gate").classList.toggle("is-hidden", ok);
  document.getElementById("console-content").classList.toggle("is-hidden", !ok);
  if (navRef?.setAuthButtons) navRef.setAuthButtons(ok);
  if (!ok) document.getElementById("session-info").textContent = "未登录";
}

function show(id, obj) {
  document.getElementById(id).textContent =
    typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
}

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
  if (!resp.ok || (data.code && data.code !== "OK")) {
    throw new Error(data.message || `HTTP ${resp.status}`);
  }
  return data.data;
}

function logout() {
  state.token = "";
  state.tenantId = "";
  state.user = null;
  localStorage.removeItem("base_token");
  localStorage.removeItem("base_tenant");
  setAuthed(false);
  BaseUI.toast("已退出");
  openLogin();
}

function openLogin() {
  BaseUI.openLoginModal({
    requireAuth: true,
    onSubmit: async (form) => {
      const data = await api("/auth/login", { method: "POST", body: form });
      state.token = data.access_token;
      state.tenantId = data.tenant_id || "";
      localStorage.setItem("base_token", state.token);
      if (state.tenantId) localStorage.setItem("base_tenant", state.tenantId);
      await afterLogin();
    },
  });
}

async function afterLogin() {
  state.user = await api("/auth/user-info");
  document.getElementById("session-info").textContent =
    `${state.user.username} @ ${state.user.tenant_id || state.tenantId || "-"}`;
  setAuthed(true);
  await Promise.all([loadAgents(), loadModels()]).catch(() => {});
  BaseUI.toast("登录成功");
}

async function loadAgents() {
  const list = await api("/agent/list");
  const select = document.getElementById("agent-id");
  if (!list.length) {
    select.innerHTML = `<option value="">暂无智能体，请先登记</option>`;
  } else {
    select.innerHTML = list
      .map(
        (a) =>
          `<option value="${a.agent_id}">${a.agent_name || a.agent_id}（剩 ${a.quota?.remain_value ?? "-"}）</option>`
      )
      .join("");
  }
  show("agent-out", list);
}

async function loadModels() {
  const list = await api("/model/list");
  const select = document.getElementById("model-id");
  const active = (list || []).filter((m) => m.status === "active");
  select.innerHTML = active
    .map((m) => `<option value="${m.model_id}">${m.model_name} (${m.provider || "mock"})</option>`)
    .join("");
}

function bindTabs() {
  document.querySelectorAll(".cap-tab").forEach((tab) => {
    tab.onclick = () => {
      document.querySelectorAll(".cap-tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".cap-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.querySelector(`[data-panel="${tab.dataset.tab}"]`)?.classList.add("active");
    };
  });
}

function bindActions() {
  document.getElementById("btn-gate-login").onclick = openLogin;

  // IAM
  document.getElementById("btn-perm").onclick = () =>
    api("/iam/my-permissions").then((d) => show("perm-out", d)).catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-users").onclick = () =>
    api("/iam/users").then((d) => show("iam-out", d)).catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-roles").onclick = () =>
    api("/iam/roles").then((d) => show("iam-out", d)).catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-register").onclick = () =>
    api("/iam/register", {
      method: "POST",
      body: {
        username: document.getElementById("reg-username").value.trim(),
        password: document.getElementById("reg-password").value,
      },
    })
      .then((d) => {
        show("iam-out", d);
        BaseUI.toast("用户已注册");
      })
      .catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-create-role").onclick = () =>
    api("/iam/roles", {
      method: "POST",
      body: {
        role_name: document.getElementById("role-name").value.trim(),
        permissions: document
          .getElementById("role-perms")
          .value.split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      },
    })
      .then((d) => {
        show("iam-out", d);
        BaseUI.toast("角色已创建");
      })
      .catch((e) => BaseUI.toast(e.message));

  // Gateway
  document.getElementById("btn-chat").onclick = async () => {
    try {
      const data = await api("/gateway/chat/completions", {
        method: "POST",
        body: {
          agent_id: document.getElementById("agent-id").value,
          model: document.getElementById("model-id").value || "mock-gpt",
          messages: [{ role: "user", content: document.getElementById("chat-input").value }],
        },
      });
      show("chat-out", data);
      await loadAgents();
    } catch (e) {
      BaseUI.toast(e.message);
    }
  };
  document.getElementById("btn-stat").onclick = () =>
    api("/gateway/call-stat").then((d) => show("stat-out", d)).catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-billing").onclick = () =>
    api("/gateway/billing").then((d) => show("stat-out", d)).catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-reg-agent").onclick = () =>
    api("/agent/register", {
      method: "POST",
      body: {
        agent_id: document.getElementById("new-agent-id").value.trim() || null,
        agent_name: document.getElementById("new-agent-name").value.trim(),
        quota_limit: Number(document.getElementById("new-agent-quota").value || 100000),
      },
    })
      .then(async (d) => {
        show("agent-out", d);
        BaseUI.toast("智能体已登记");
        await loadAgents();
      })
      .catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-refresh-agents").onclick = () =>
    loadAgents().catch((e) => BaseUI.toast(e.message));

  // KB
  document.getElementById("btn-kb-create").onclick = () =>
    api("/kb/repo/create", {
      method: "POST",
      body: { repo_name: document.getElementById("kb-name").value.trim() },
    })
      .then((d) => {
        document.getElementById("kb-repo-id").value = d.repo_id;
        document.getElementById("wf-repo-id").value = d.repo_id;
        show("kb-out", d);
      })
      .catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-kb-list").onclick = () =>
    api("/kb/repo/list").then((d) => show("kb-out", d)).catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-kb-upload").onclick = async () => {
    try {
      const repo_id = document.getElementById("kb-repo-id").value.trim();
      if (!repo_id) throw new Error("请先创建或填写仓库 ID");
      const text = document.getElementById("kb-text").value;
      const fd = new FormData();
      fd.append("repo_id", repo_id);
      fd.append("tags", "culture");
      fd.append("file", new Blob([text], { type: "text/plain" }), "culture.txt");
      const d = await api("/kb/repo/document/upload", { method: "POST", formData: fd });
      show("kb-out", d);
    } catch (e) {
      BaseUI.toast(e.message);
    }
  };
  document.getElementById("btn-kb-docs").onclick = () => {
    const repo_id = document.getElementById("kb-repo-id").value.trim();
    if (!repo_id) return BaseUI.toast("请填写仓库 ID");
    api(`/kb/repo/${repo_id}/documents`).then((d) => show("kb-out", d)).catch((e) => BaseUI.toast(e.message));
  };
  document.getElementById("btn-kb-snap").onclick = () => {
    const repo_id = document.getElementById("kb-repo-id").value.trim();
    if (!repo_id) return BaseUI.toast("请填写仓库 ID");
    api(`/kb/repo/${repo_id}/snapshot?note=manual`, { method: "POST" })
      .then((d) => show("kb-out", d))
      .catch((e) => BaseUI.toast(e.message));
  };
  document.getElementById("btn-kb-search").onclick = () =>
    api("/kb/repo/search", {
      method: "POST",
      body: {
        repo_id: document.getElementById("kb-repo-id").value.trim(),
        query: document.getElementById("kb-query").value.trim(),
        top_n: 5,
      },
    })
      .then((d) => show("kb-out", d))
      .catch((e) => BaseUI.toast(e.message));

  // Workflow
  document.getElementById("btn-prompt-save").onclick = () =>
    api("/prompt/template/save", {
      method: "POST",
      body: {
        name: document.getElementById("prompt-name").value.trim(),
        content: document.getElementById("prompt-content").value,
      },
    })
      .then((d) => show("wf-out", d))
      .catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-prompt-list").onclick = () =>
    api("/prompt/template/list").then((d) => show("wf-out", d)).catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-wf-run").onclick = () =>
    api("/workflow/run", {
      method: "POST",
      body: {
        name: "文化RAG",
        dsl: {
          steps: [
            { id: "r1", type: "retrieve", top_n: 3 },
            {
              id: "l1",
              type: "llm",
              model_id: "mock-gpt",
              context_from: "r1",
              prompt: "基于资料回答。\n问题：{query}\n资料：{context}",
            },
          ],
        },
        input: {
          repo_id: document.getElementById("wf-repo-id").value.trim(),
          query: document.getElementById("wf-query").value.trim(),
        },
      },
    })
      .then((d) => show("wf-out", d))
      .catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-wf-list").onclick = () =>
    api("/workflow/list").then((d) => show("wf-out", d)).catch((e) => BaseUI.toast(e.message));

  // Plugin
  document.getElementById("btn-pg-reg").onclick = () =>
    api("/plugin/register", {
      method: "POST",
      body: {
        name: document.getElementById("pg-name").value.trim(),
        endpoint: document.getElementById("pg-endpoint").value.trim(),
        method: "POST",
        category: "debug",
        param_schema: {},
      },
    })
      .then((d) => {
        document.getElementById("pg-id").value = d.plugin_id;
        show("pg-out", d);
      })
      .catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-pg-list").onclick = () =>
    api("/plugin/list").then((d) => show("pg-out", d)).catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-pg-market").onclick = () =>
    api("/plugin/marketplace").then((d) => show("pg-out", d)).catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-pg-call").onclick = () => {
    let params = {};
    try {
      params = JSON.parse(document.getElementById("pg-params").value || "{}");
    } catch {
      return BaseUI.toast("参数 JSON 无效");
    }
    api("/plugin/call", {
      method: "POST",
      body: { plugin_id: document.getElementById("pg-id").value.trim(), params },
    })
      .then((d) => show("pg-out", d))
      .catch((e) => BaseUI.toast(e.message));
  };
  document.getElementById("btn-pg-logs").onclick = () =>
    api("/plugin/call-logs").then((d) => show("pg-out", d)).catch((e) => BaseUI.toast(e.message));

  // Compliance
  document.getElementById("btn-cmp-save").onclick = () =>
    api("/compliance/config", {
      method: "POST",
      body: {
        title: document.getElementById("cmp-title").value.trim(),
        content: document.getElementById("cmp-content").value,
        mask_phone: true,
        mask_id_card: true,
        mask_email: true,
      },
    })
      .then((d) => {
        show("cmp-out", d);
        BaseUI.toast("合规配置已保存");
      })
      .catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-cmp-load").onclick = () =>
    api("/compliance/config").then((d) => show("cmp-out", d)).catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-cmp-show").onclick = async () => {
    try {
      const cfg = await api("/compliance/config");
      BaseUI.openDisclaimer({ title: cfg.title, content: cfg.content });
    } catch (e) {
      BaseUI.toast(e.message);
    }
  };
  document.getElementById("btn-mask").onclick = () =>
    api("/compliance/mask-preview", {
      method: "POST",
      body: { text: document.getElementById("mask-text").value },
    })
      .then((d) => show("cmp-out", d))
      .catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-audit").onclick = () =>
    api("/log/audit/list?page=1&page_size=20").then((d) => show("cmp-out", d)).catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-sessions").onclick = () =>
    api("/log/sessions").then((d) => show("cmp-out", d)).catch((e) => BaseUI.toast(e.message));
}

window.addEventListener("DOMContentLoaded", async () => {
  navRef = BaseUI.mountNav({
    brand: "文化智能体 · 基座平台",
    onLogin: openLogin,
    onLogout: logout,
    onProfile: () => {
      if (!state.user) return openLogin();
      BaseUI.openProfile({ user: state.user });
    },
    onDisclaimer: async () => {
      try {
        const cfg = await api("/compliance/config");
        BaseUI.openDisclaimer({ title: cfg.title, content: cfg.content });
      } catch {
        BaseUI.openDisclaimer({
          content: "本基座提供合规框架组件，业务合规由子平台负责。",
        });
      }
    },
  });
  setAuthed(false);
  bindTabs();
  bindActions();

  try {
    if (!state.token) openLogin();
    else await afterLogin();
  } catch (e) {
    logout();
  }
});
