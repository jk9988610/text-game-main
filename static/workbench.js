const authPanel = AuthPanel.create();
document.getElementById("auth-panel").appendChild(authPanel.root);
const lists = document.getElementById("lists");
const filter = document.getElementById("filter");
const notice = document.getElementById("notice");
const headings = { submitted: "我提交的申请", tasks: "分配给我的任务", approvals: "等待我审批", completed: "已完成" };
const appTitles = { request_form_demo: "申请审批流程", task_flow_demo: "任务流程示例", first_branch: "互动故事" };
let data = {};

function setNotice(message, error = false) {
  notice.textContent = message;
  notice.dataset.error = error ? "true" : "false";
}

function appLink(instance) {
  const target = instance.app_id === "request_form_demo" ? "form" : instance.app_id === "task_flow_demo" ? "task" : "story";
  return `/apps/${encodeURIComponent(instance.app_id)}?instance=${encodeURIComponent(instance.instance_id)}#${target}`;
}

function renderInstance(instance) {
  const link = document.createElement("a");
  link.className = "instance";
  link.href = appLink(instance);
  const title = document.createElement("h3");
  title.textContent = appTitles[instance.app_id] || instance.app_id;
  const detail = document.createElement("p");
  detail.textContent = `状态：${instance.status} · 更新：${instance.updated_at || "未知"}`;
  link.append(title, detail);
  return link;
}

function renderGroup(key, items) {
  const group = document.createElement("section");
  group.className = "list-group";
  const heading = document.createElement("h2");
  heading.textContent = headings[key];
  group.appendChild(heading);
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "暂无流程";
    group.appendChild(empty);
  } else items.forEach((item) => group.appendChild(renderInstance(item)));
  return group;
}

function render() {
  lists.replaceChildren();
  const keys = filter.value === "all" ? Object.keys(headings) : [filter.value];
  keys.forEach((key) => lists.appendChild(renderGroup(key, data[key] || [])));
}

async function load() {
  setNotice("加载中…");
  try {
    const response = await fetch("/api/workbench", { headers: { "Accept": "application/json" } });
    const text = await response.text();
    let payload;
    try { payload = JSON.parse(text); } catch (_) { throw new Error(`工作台接口返回了 HTML（HTTP ${response.status}），请重启 Flask 服务并刷新页面`); }
    if (!response.ok || payload.success === false) throw new Error(payload.message || "工作台加载失败");
    data = payload;
    render();
    setNotice(payload.demo ? "当前为演示用户" : "已按当前账号筛选");
  } catch (error) {
    setNotice(error.message, true);
  }
}

filter.addEventListener("change", render);
document.getElementById("refresh").addEventListener("click", load);
load();
