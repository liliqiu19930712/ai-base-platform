/**
 * 基座公共前端组件库（MVP）
 * 子平台可复用：导航、登录弹窗、消息通知、合规免责弹窗、个人中心入口
 */
(function (global) {
  const BaseUI = {
    toast(message, ms = 2600) {
      let el = document.getElementById("base-toast");
      if (!el) {
        el = document.createElement("div");
        el.id = "base-toast";
        el.className = "base-toast";
        document.body.appendChild(el);
      }
      el.textContent = message;
      el.classList.add("show");
      clearTimeout(el._timer);
      el._timer = setTimeout(() => el.classList.remove("show"), ms);
    },

    mountNav({ brand = "智能体基座平台", onLogin, onLogout, onProfile, onDisclaimer } = {}) {
      const nav = document.createElement("header");
      nav.className = "base-nav";
      nav.innerHTML = `
        <div class="base-brand">
          <div class="base-brand-mark"></div>
          <span>${brand}</span>
        </div>
        <div class="base-nav-actions">
          <button class="base-btn ghost" data-act="disclaimer">合规提示</button>
          <button class="base-btn ghost" data-act="profile">个人中心</button>
          <button class="base-btn ghost is-hidden" data-act="logout">退出登录</button>
          <button class="base-btn primary" data-act="login">登录</button>
        </div>
      `;
      document.body.prepend(nav);
      nav.addEventListener("click", (e) => {
        const act = e.target?.dataset?.act;
        if (act === "login" && onLogin) onLogin();
        if (act === "logout" && onLogout) onLogout();
        if (act === "profile" && onProfile) onProfile();
        if (act === "disclaimer" && onDisclaimer) onDisclaimer();
      });
      nav.setAuthButtons = (loggedIn) => {
        const loginBtn = nav.querySelector('[data-act="login"]');
        const logoutBtn = nav.querySelector('[data-act="logout"]');
        if (loginBtn) loginBtn.classList.toggle("is-hidden", !!loggedIn);
        if (logoutBtn) logoutBtn.classList.toggle("is-hidden", !loggedIn);
      };
      nav.setAuthButtons(false);
      return nav;
    },

    openModal({
      title,
      bodyHtml,
      onConfirm,
      confirmText = "确定",
      closable = true,
      showCancel = true,
    } = {}) {
      let mask = document.getElementById("base-modal-mask");
      if (!mask) {
        mask = document.createElement("div");
        mask.id = "base-modal-mask";
        mask.className = "base-modal-mask";
        mask.innerHTML = `<div class="base-modal" role="dialog"></div>`;
        document.body.appendChild(mask);
        mask.addEventListener("click", (e) => {
          if (e.target === mask && mask.dataset.closable !== "0") {
            mask.classList.remove("open");
          }
        });
      }
      mask.dataset.closable = closable ? "1" : "0";
      const modal = mask.querySelector(".base-modal");
      modal.innerHTML = `
        <h3>${title}</h3>
        <div>${bodyHtml}</div>
        <div class="row" style="margin-top:16px">
          ${showCancel && closable ? `<button class="base-btn ghost" data-close>取消</button>` : ""}
          <button class="base-btn primary" data-ok>${confirmText}</button>
        </div>
      `;
      mask.classList.add("open");
      const closeBtn = modal.querySelector("[data-close]");
      if (closeBtn) {
        closeBtn.onclick = () => {
          if (closable) mask.classList.remove("open");
        };
      }
      modal.querySelector("[data-ok]").onclick = async () => {
        try {
          if (onConfirm) await onConfirm(modal);
          mask.classList.remove("open");
        } catch (err) {
          // 登录失败时保持弹窗
          if (err && err.message) BaseUI.toast(err.message);
        }
      };
      return modal;
    },

    async fillLoginTenants(username) {
      const select = document.getElementById("login-tenant");
      const hint = document.getElementById("login-tenant-hint");
      if (!select) return;
      const prev = select.value;
      select.innerHTML = `<option value="">加载中...</option>`;
      try {
        const q = username ? `?username=${encodeURIComponent(username)}` : "";
        const resp = await fetch(`/api/v1/auth/login-tenants${q}`);
        const data = await resp.json();
        const list = data.data || [];
        if (!list.length) {
          select.innerHTML = `<option value="">该账号暂无可用租户</option>`;
          if (hint) {
            hint.textContent =
              "提示：新建租户要用创建时设置的管理员账号登录；demo 只能进已绑定的教育/企业租户。";
          }
          return;
        }
        select.innerHTML = list
          .map(
            (t) =>
              `<option value="${t.tenant_id}">${t.tenant_name}（${t.tenant_id}）</option>`
          )
          .join("");
        if (prev && list.some((t) => t.tenant_id === prev)) {
          select.value = prev;
        }
        if (hint) {
          hint.textContent = `共 ${list.length} 个可选租户（含管理后台新建的）`;
        }
      } catch (e) {
        select.innerHTML = `<option value="">租户列表加载失败</option>`;
        if (hint) hint.textContent = e.message || "加载失败";
      }
    },

    openLoginModal({ onSubmit, requireAuth = false } = {}) {
      const uid = `u_${Date.now()}`;
      const modal = this.openModal({
        title: "基座统一登录",
        confirmText: "登录",
        closable: !requireAuth,
        showCancel: !requireAuth,
        bodyHtml: `
          <p class="muted">请自行输入账号密码，并选择租户。租户列表会随账号自动刷新。</p>
          <label>用户名</label>
          <input id="login-username" name="${uid}_user" value="" placeholder="请输入用户名" autocomplete="off" readonly />
          <label>密码</label>
          <input id="login-password" name="${uid}_pass" type="password" value="" placeholder="请输入密码" autocomplete="new-password" readonly />
          <label>租户</label>
          <select id="login-tenant"><option value="">加载中...</option></select>
          <p class="muted" id="login-tenant-hint" style="margin-top:8px"></p>
        `,
        onConfirm: async () => {
          const username = document.getElementById("login-username").value.trim();
          const password = document.getElementById("login-password").value;
          const tenant_id = document.getElementById("login-tenant").value || null;
          if (!username || !password) {
            throw new Error("请输入用户名和密码");
          }
          if (onSubmit) await onSubmit({ username, password, tenant_id });
        },
      });
      const usernameInput = document.getElementById("login-username");
      const passwordInput = document.getElementById("login-password");
      const unlock = (el) => {
        el.removeAttribute("readonly");
      };
      usernameInput.addEventListener("focus", () => unlock(usernameInput));
      passwordInput.addEventListener("focus", () => unlock(passwordInput));
      // 清掉浏览器自动填充
      const clearAutofill = () => {
        usernameInput.value = "";
        passwordInput.value = "";
      };
      clearAutofill();
      setTimeout(clearAutofill, 50);
      setTimeout(clearAutofill, 300);
      const refresh = () => this.fillLoginTenants(usernameInput.value.trim());
      usernameInput.addEventListener("blur", refresh);
      usernameInput.addEventListener("change", refresh);
      this.fillLoginTenants("");
      return modal;
    },

    openDisclaimer({ title = "合规免责提示", content = "" } = {}) {
      return this.openModal({
        title,
        confirmText: "我已知晓",
        bodyHtml: `<p class="muted">${content || "本提示文案由子平台传入。基座只提供弹窗框架，不做业务合规判定。"}</p>`,
      });
    },

    openProfile({ user }) {
      const info = user
        ? `<p>用户：${user.username || "-"}</p><p>租户：${user.tenant_id || "-"}</p>`
        : `<p class="muted">尚未登录</p>`;
      return this.openModal({
        title: "个人中心",
        confirmText: "关闭",
        bodyHtml: info,
      });
    },
  };

  global.BaseUI = BaseUI;
})(window);
