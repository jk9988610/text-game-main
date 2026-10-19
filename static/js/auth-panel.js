/* 共享账号、组织和标签弹窗。 */
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
    root.innerHTML = `<button class="account-button" type="button">账号 / 组织</button><dialog class="account-dialog"><div class="dialog-head"><strong>账号与组织</strong><button class="dialog-close" type="button" aria-label="关闭">×</button></div><div class="account-summary"><strong class="auth-name">演示用户</strong><span class="auth-org"></span><span class="auth-roles"></span></div><div class="auth-actions"><button class="auth-toggle" type="button">登录 / 注册</button><button class="org-manage-toggle" type="button">组织管理</button></div><form class="auth-form" hidden><input name="username" placeholder="用户名" autocomplete="username" required><input name="password" type="password" placeholder="密码" autocomplete="current-password" required><div><button class="auth-login" type="submit">登录</button><button class="auth-register" type="button">注册</button></div></form><section class="org-actions" hidden><div><input class="org-name" placeholder="新组织名称"><button class="org-create" type="button">创建组织</button></div><div><input class="org-code" placeholder="组织邀请码"><button class="org-join" type="button">加入组织</button></div><label>当前组织 <select class="org-select"></select></label><p class="invite-hint" hidden></p><button class="invite-copy" type="button" hidden>复制邀请码</button></section><p class="auth-error" hidden></p></dialog>`;
    const dialog = root.querySelector(".account-dialog");
    const name = root.querySelector(".auth-name");
    const org = root.querySelector(".auth-org");
    const roles = root.querySelector(".auth-roles");
    const form = root.querySelector(".auth-form");
    const orgActions = root.querySelector(".org-actions");
    const orgSelect = root.querySelector(".org-select");
    const error = root.querySelector(".auth-error");
    const invite = root.querySelector(".invite-hint");
    const copyInvite = root.querySelector(".invite-copy");
    function showError(message) { error.textContent = message; error.hidden = false; }
    function render(value) {
      context = value.user || value;
      name.textContent = context.username || "演示用户";
      org.textContent = context.active_organization ? `组织：${context.active_organization.name}` : "未选择组织";
      roles.textContent = (context.roles || []).join(" · ") || "演示";
      root.querySelector(".auth-toggle").textContent = context.demo ? "登录 / 注册" : "退出登录";
      orgActions.hidden = Boolean(context.demo);
      orgSelect.replaceChildren();
      (context.organizations || []).forEach((item) => { const option = document.createElement("option"); option.value = item.id; option.textContent = item.name; option.selected = context.active_organization?.id === item.id; orgSelect.appendChild(option); });
      const active = context.active_organization;
      invite.hidden = !active;
      copyInvite.hidden = !active;
      if (active) invite.textContent = `组织邀请码：${active.join_code}`;
      options.onChange?.(context);
    }
    root.querySelector(".account-button").onclick = () => { if (!dialog.open) dialog.showModal(); };
    root.querySelector(".dialog-close").onclick = () => dialog.close();
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
    root.querySelector(".auth-toggle").onclick = async () => { if (context?.demo) { form.hidden = !form.hidden; return; } try { await request("/api/auth/logout", { method: "POST" }); render(await request("/api/auth/roles")); } catch (e) { showError(e.message); } };
    form.onsubmit = async (event) => { event.preventDefault(); try { const data = new FormData(form); await request("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(data.entries())) }); render(await request("/api/auth/roles")); form.hidden = true; } catch (e) { showError(e.message); } };
    root.querySelector(".auth-register").onclick = async () => { try { const data = new FormData(form); await request("/api/auth/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(data.entries())) }); render(await request("/api/auth/roles")); form.hidden = true; } catch (e) { showError(e.message); } };
    copyInvite.onclick = async () => { try { await navigator.clipboard.writeText(context.active_organization.join_code); copyInvite.textContent = "已复制"; } catch (_) { showError("复制失败，请手动选择邀请码"); } };
    root.querySelector(".org-manage-toggle").onclick = () => { orgActions.hidden = !orgActions.hidden; };
    root.querySelector(".org-create").onclick = async () => { try { await request("/api/organizations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: root.querySelector(".org-name").value }) }); render(await request("/api/auth/roles")); } catch (e) { showError(e.message); } };
    root.querySelector(".org-join").onclick = async () => { try { await request("/api/organizations/join", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ join_code: root.querySelector(".org-code").value }) }); render(await request("/api/auth/roles")); } catch (e) { showError(e.message); } };
    orgSelect.onchange = async () => { try { await request("/api/organizations/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ organization_id: Number(orgSelect.value) }) }); render(await request("/api/auth/roles")); } catch (e) { showError(e.message); } };
    request("/api/auth/roles").then(render).catch(showError);
    return { root, getContext: () => context, refresh: () => request("/api/auth/roles").then(render) };
  }
  return { create };
})();
