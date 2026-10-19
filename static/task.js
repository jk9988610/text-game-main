const authPanel = AuthPanel.create();
document.getElementById("auth-panel").appendChild(authPanel.root);
const $ = (id) => document.getElementById(id);
function render(payload) {
  const node = payload.node || {};
  $("title").textContent = payload.title || "任务流程";
  const process = payload.process; if (process) $("process-summary").textContent = `状态：${process.status} · 申请人：${process.applicant_id || "未指定"} · 处理人：${process.handler_id || "未分配"}`;
  $("description").textContent = payload.description || "";
  $("node-id").textContent = payload.node_id ? `NODE / ${payload.node_id}` : "FLOW COMPLETE";
  $("node-title").textContent = node.title || "流程结束";
  $("node-content").textContent = node.content || "";
  const box = $("transitions"); box.replaceChildren();
  if (!(node.transitions || []).length) { const empty = document.createElement("p"); empty.className = "empty-transitions"; empty.textContent = "此任务流程尚未配置下一步转移。管理员可打开任务编辑器添加转移。"; box.appendChild(empty); }
  (node.transitions || []).forEach((transition, index) => {
    const button = document.createElement("button"); button.className = "transition"; button.type = "button"; button.textContent = transition.label || `转移 ${index + 1}`;
    button.addEventListener("click", () => advance(index)); box.appendChild(button);
  });
  const history = payload.state?.records?.history || []; $("history").replaceChildren();
  history.forEach((item) => { const li = document.createElement("li"); li.textContent = item; $("history").appendChild(li); });
  $("assignee").textContent = payload.state?.variables?.assignee ? `处理人：${payload.state.variables.assignee}` : "尚未接手";
  $("error").hidden = true;
}
function showError(message) { $("error").textContent = message || "请求失败"; $("error").hidden = false; }
async function createTask() { try { const r = await fetch("/api/apps/task_flow_demo/process", {method:"POST"}); const p = await r.json(); if (!r.ok || p.success === false) throw new Error(p.message); await load(); } catch (e) { showError(e.message); } }
$("new-task").addEventListener("click", createTask);

async function advance(index) { document.querySelectorAll(".transition").forEach((b) => b.disabled = true); try { const r = await fetch("/api/apps/task_flow_demo/transition", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({index})}); const p = await r.json(); if (!r.ok || p.success === false) throw new Error(p.message); render(p); } catch (e) { showError(e.message); document.querySelectorAll(".transition").forEach((b) => b.disabled = false); } }
$("reset").addEventListener("click", async () => { try { const r = await fetch("/api/apps/task_flow_demo/reset", {method:"POST"}); render(await r.json()); } catch (e) { showError(e.message); } });
const savePanel = AppSavePanel.create({ appId: "task_flow_demo", onState: render });
$("save-panel").appendChild(savePanel.root);
(async () => {
  try {
    await AppSavePanel.chooseResume({ appId: "task_flow_demo", onState: render });
    await load();
    await savePanel.refresh();
  } catch (error) { showError(error.message); }
})();
