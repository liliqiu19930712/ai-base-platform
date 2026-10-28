const state = {
  // 管理后台只用独立 token，避免演示台 demo 登录态串进来
  token: localStorage.getItem("base_admin_token") || "",
  user: null,
};

let navRef = null;

function setAuthed(ok) {
  const gate = document.getElementById("auth-gate");
  const content = document.getElementById("admin-content");
  if (gate) gate.classList.toggle("is-hidden", ok);
  if (content) content.classList.toggle("is-hidden", !ok);
  if (navRef?.setAuthButtons) navRef.setAuthButtons(ok);
  if (!ok) {
    document.getElementById("session-info").textContent = "未登录";
    const list = document.getElementById("tenant-list");
    if (list) list.innerHTML = "";
    const out = document.getElementById("create-out");
    if (out) out.textContent = "{}";
  }
}

function logout() {
  state.token = "";
  state.user = null;
  localStorage.removeItem("base_admin_token");
  setAuthed(false);
  BaseUI.toast("已退出登录");
  openAdminLogin();
}

async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const resp = await fetch(`/api/v1${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || (data.code && data.code !== "OK")) {
    throw new Error(data.message || `HTTP ${resp.status}`);
  }
  return data.data;
}

function val(id) {
  return document.getElementById(id).value.trim();
}

function checked(id) {
  return document.getElementById(id).checked;
}

function openAdminLogin() {
  const uid = `admin_${Date.now()}`;
  BaseUI.openModal({
    title: "平台管理员登录",
    confirmText: "登录",
    closable: false,
    showCancel: false,
    bodyHtml: `
      <p class="muted">请输入平台管理员账号密码（无需选择租户）</p>
      <label>用户名</label>
      <input id="login-username" name="${uid}_user" value="" placeholder="请输入用户名" autocomplete="off" readonly />
      <label>密码</label>
      <input id="login-password" name="${uid}_pass" type="password" value="" placeholder="请输入密码" autocomplete="new-password" readonly />
    `,
    onConfirm: async () => {
      const usernameInput = document.getElementById("login-username");
      const passwordInput = document.getElementById("login-password");
      usernameInput.removeAttribute("readonly");
      passwordInput.removeAttribute("readonly");
      const username = usernameInput.value.trim();
      const password = passwordInput.value;
      if (!username || !password) {
        throw new Error("请输入用户名和密码");
      }
      await doLogin({ username, password });
    },
  });
  const usernameInput = document.getElementById("login-username");
  const passwordInput = document.getElementById("login-password");
  const unlock = (el) => el.removeAttribute("readonly");
  usernameInput.addEventListener("focus", () => unlock(usernameInput));
  passwordInput.addEventListener("focus", () => unlock(passwordInput));
  const clearAutofill = () => {
    usernameInput.value = "";
    passwordInput.value = "";
  };
  clearAutofill();
  setTimeout(clearAutofill, 50);
  setTimeout(clearAutofill, 300);
}

async function doLogin(form) {
  const data = await api("/auth/login", {
    method: "POST",
    body: {
      username: form.username,
      password: form.password,
      tenant_id: form.tenant_id || null,
    },
  });
  if (!data.is_platform_admin) {
    throw new Error("当前账号不是平台管理员");
  }
  state.token = data.access_token;
  localStorage.setItem("base_admin_token", state.token);
  await refreshSession();
  setAuthed(true);
  BaseUI.toast("管理员登录成功");
  await loadTenants();
}

async function refreshSession() {
  if (!state.token) return;
  state.user = await api("/auth/user-info");
  if (!state.user.is_platform_admin) {
    throw new Error("需要平台管理员权限");
  }
  document.getElementById("session-info").textContent =
    `${state.user.username}（平台管理员）`;
}

function renderTenants(list) {
  const root = document.getElementById("tenant-list");
  if (!list.length) {
    root.innerHTML = `<p class="muted">暂无租户</p>`;
    return;
  }
  root.innerHTML = list
    .map((t) => {
      const f = t.features || {};
      const quotaText = (t.quotas || [])
        .map((q) => `${q.agent_id}: ${q.used_value}/${q.limit_value}`)
        .join("；") || "暂无配额";
      const admins = (t.admins || []).map((a) => a.username).join(", ") || "-";
      return `
        <article class="tenant-card" data-id="${t.tenant_id}">
          <header>
            <div>
              <h3>${t.tenant_name}</h3>
              <div class="muted">${t.tenant_id} · ${t.tenant_desc || "无描述"}</div>
            </div>
            <span class="badge ${t.status}">${t.status}</span>
          </header>
          <div>
            <span class="tag ${f.enable_gateway ? "on" : "off"}">网关</span>
            <span class="tag ${f.enable_kb ? "on" : "off"}">知识库</span>
            <span class="tag ${f.enable_workflow ? "on" : "off"}">工作流</span>
            <span class="tag ${f.enable_plugin ? "on" : "off"}">插件</span>
          </div>
          <p class="muted" style="margin:8px 0 0">管理员：${admins}</p>
          <p class="muted" style="margin:4px 0 0">配额：${quotaText}</p>
          <p class="muted" style="margin:4px 0 0">凭证：<code>${f.api_credential || "-"}</code></p>
          <div class="tenant-actions">
            <button class="base-btn" data-act="toggle-status">${t.status === "active" ? "停用" : "启用"}</button>
            <button class="base-btn" data-act="toggle-kb">${f.enable_kb ? "关闭知识库" : "开通知识库"}</button>
            <button class="base-btn" data-act="rotate">轮换凭证</button>
            <input type="number" data-quota value="${f.default_quota_limit || 100000}" />
            <button class="base-btn primary" data-act="quota">更新默认配额</button>
          </div>
        </article>
      `;
    })
    .join("");

  root.querySelectorAll(".tenant-card").forEach((card) => {
    const tenantId = card.dataset.id;
    card.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-act]");
      if (!btn) return;
      const act = btn.dataset.act;
      try {
        if (act === "toggle-status") {
          const next = card.querySelector(".badge").textContent.trim() === "active" ? "disabled" : "active";
          await api(`/admin/tenants/${tenantId}`, { method: "PATCH", body: { status: next } });
          BaseUI.toast(next === "active" ? "已启用" : "已停用");
        } else if (act === "toggle-kb") {
          const kbOn = [...card.querySelectorAll(".tag")].some(
            (el) => el.textContent.includes("知识库") && el.classList.contains("on")
          );
          await api(`/admin/tenants/${tenantId}`, {
            method: "PATCH",
            body: { enable_kb: !kbOn },
          });
          BaseUI.toast(!kbOn ? "已开通知识库" : "已关闭知识库");
        } else if (act === "rotate") {
          const data = await api(`/admin/tenants/${tenantId}/rotate-credential`, { method: "POST" });
          BaseUI.toast("凭证已轮换");
          document.getElementById("create-out").textContent = JSON.stringify(data, null, 2);
        } else if (act === "quota") {
          const limit = Number(card.querySelector("[data-quota]").value);
          await api(`/admin/tenants/${tenantId}`, {
            method: "PATCH",
            body: { default_quota_limit: limit },
          });
          await api(`/admin/tenants/${tenantId}/quota`, {
            method: "POST",
            body: { agent_id: "default_agent", limit_value: limit },
          });
          BaseUI.toast("配额已更新");
        }
        await loadTenants();
      } catch (err) {
        BaseUI.toast(err.message);
      }
    });
  });
}

async function loadTenants() {
  const list = await api("/admin/tenants");
  renderTenants(list);
}

async function createTenant() {
  if (!state.token) {
    openAdminLogin();
    throw new Error("请先登录");
  }
  const body = {
    tenant_id: val("tenant_id") || null,
    tenant_name: val("tenant_name"),
    tenant_desc: val("tenant_desc"),
    admin_username: val("admin_username"),
    admin_password: val("admin_password"),
    default_agent_id: val("default_agent_id") || "default_agent",
    default_quota_limit: Number(val("default_quota_limit") || 100000),
    contact_name: val("contact_name"),
    contact_email: val("contact_email"),
    enable_gateway: checked("enable_gateway"),
    enable_kb: checked("enable_kb"),
    enable_workflow: checked("enable_workflow"),
    enable_plugin: checked("enable_plugin"),
  };
  if (!body.tenant_name || !body.admin_username || !body.admin_password) {
    throw new Error("请填写租户名称、管理员账号和密码");
  }
  if (body.admin_password.length < 6) {
    throw new Error("管理员密码至少 6 位");
  }
  const data = await api("/admin/tenants", { method: "POST", body });
  document.getElementById("create-out").textContent = JSON.stringify(data, null, 2);
  BaseUI.toast("租户创建成功，请把账号交给子平台负责人");
  await loadTenants();
}

window.addEventListener("DOMContentLoaded", async () => {
  navRef = BaseUI.mountNav({
    brand: "智能体基座 · 管理后台",
    onLogin: () => openAdminLogin(),
    onLogout: () => logout(),
    onProfile: () => {
      if (!state.user) {
        openAdminLogin();
        return;
      }
      BaseUI.openProfile({ user: state.user });
    },
    onDisclaimer: () =>
      BaseUI.openDisclaimer({
        content: "管理后台仅限基座运维人员使用，负责子平台准入与配额治理。",
      }),
  });
  setAuthed(false);

  const nav = document.querySelector(".base-nav-actions");
  if (nav) {
    const link = document.createElement("a");
    link.className = "base-btn ghost";
    link.href = "/";
    link.textContent = "演示台";
    nav.prepend(link);
  }

  document.getElementById("btn-gate-login").onclick = () => openAdminLogin();
  document.getElementById("btn-create").onclick = () =>
    createTenant().catch((e) => BaseUI.toast(e.message));
  document.getElementById("btn-refresh").onclick = () => {
    if (!state.token) return openAdminLogin();
    loadTenants().catch((e) => BaseUI.toast(e.message));
  };

  try {
    if (!state.token) {
      openAdminLogin();
    } else {
      await refreshSession();
      setAuthed(true);
      await loadTenants();
    }
  } catch (e) {
    state.token = "";
    state.user = null;
    localStorage.removeItem("base_admin_token");
    setAuthed(false);
    BaseUI.toast(e.message);
    openAdminLogin();
  }
});
