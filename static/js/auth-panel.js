/* 共享账号与角色弹窗。 */
window.AuthPanel = (() => {
  let context = null;
  const request = (path, init = {}) => fetch(path, init).then(async (response) => {
    const text = await response.text();
    let payload;
    try { payload = JSON.parse(text); } catch (_) { throw new Error(`接口 ${path} 返回了非 JSON 响应（HTTP ${response.status}）`); }
    if (!response.ok || payload.success === false) throw new Error(payload.message || "请求失败");
    return payload;
  });

  function create(options = {}) {
    const root = document.createElement("div");
    root.className = "auth-panel";
    root.innerHTML = `<button class="account-button" type="button">账号</button><dialog class="account-dialog"><div class="dialog-head"><strong>账号</strong><button class="dialog-close" type="button" aria-label="关闭">×</button></div><div class="account-summary"><strong class="auth-name">演示用户</strong><span class="auth-roles"></span></div><div class="auth-actions"><button class="auth-toggle" type="button">登录 / 注册</button></div><form class="auth-form" hidden><input name="username" placeholder="用户名" autocomplete="username" required><input name="password" type="password" placeholder="密码" autocomplete="current-password" required><div><button class="auth-login" type="submit">登录</button><button class="auth-register" type="button">注册</button></div></form><p class="auth-error" hidden></p></dialog>`;
    const dialog = root.querySelector(".account-dialog");
    const name = root.querySelector(".auth-name");
    const roles = root.querySelector(".auth-roles");
    const form = root.querySelector(".auth-form");
    const error = root.querySelector(".auth-error");
    function showError(message) { error.textContent = message; error.hidden = false; }
    function render(value) {
      context = value.user || value;
      name.textContent = context.username || "演示用户";
      roles.textContent = (context.roles || []).join(" · ") || "演示";
      root.querySelector(".auth-toggle").textContent = context.demo ? "登录 / 注册" : "退出登录";
      options.onChange?.(context);
    }
    root.querySelector(".account-button").onclick = () => { if (!dialog.open) dialog.showModal(); };
    root.querySelector(".dialog-close").onclick = () => dialog.close();
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
    root.querySelector(".auth-toggle").onclick = async () => { if (context?.demo) { form.hidden = !form.hidden; return; } try { await request("/api/auth/logout", { method: "POST" }); render(await request("/api/auth/roles")); } catch (e) { showError(e.message); } };
    form.onsubmit = async (event) => { event.preventDefault(); try { const data = new FormData(form); await request("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(data.entries())) }); render(await request("/api/auth/roles")); form.hidden = true; } catch (e) { showError(e.message); } };
    root.querySelector(".auth-register").onclick = async () => { try { const data = new FormData(form); await request("/api/auth/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(data.entries())) }); render(await request("/api/auth/roles")); form.hidden = true; } catch (e) { showError(e.message); } };
    request("/api/auth/roles").then(render).catch(showError);
    return { root, getContext: () => context, refresh: () => request("/api/auth/roles").then(render) };
  }
  return { create };
})();
