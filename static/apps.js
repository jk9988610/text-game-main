const typeLabels = { interactive_story: "互动故事", task_flow: "任务流程", form_flow: "表单流程" };
const authPanel = AuthPanel.create();
document.getElementById("auth-panel").appendChild(authPanel.root);
const apps = document.getElementById("apps");
function showError(message) { const node = document.getElementById("error"); node.textContent = message || "应用目录加载失败"; node.hidden = false; }
function render(items) {
  apps.replaceChildren();
  items.forEach((app) => {
    const link = document.createElement("a"); link.className = "app-card"; link.dataset.type = app.app_type; link.href = `/apps/${encodeURIComponent(app.app_id)}`;
    const title = document.createElement("h2"); title.textContent = app.title || app.app_id;
    const description = document.createElement("p"); description.textContent = app.description || "暂无简介";
    const meta = document.createElement("div"); meta.className = "app-meta";
    const type = document.createElement("span"); type.textContent = typeLabels[app.app_type] || app.app_type;
    const id = document.createElement("span"); id.textContent = app.app_id;
    meta.append(type, id); link.append(title, description, meta); apps.appendChild(link);
  });
}
fetch("/api/apps").then(async (response) => { const text = await response.text(); try { return JSON.parse(text); } catch (_) { throw new Error(`应用目录接口返回了 HTML（HTTP ${response.status}）`); } }).then((payload) => { if (!payload.success) throw new Error(payload.message); render(payload.apps || []); }).catch((error) => showError(error.message));
