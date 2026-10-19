const $ = (id) => document.getElementById(id);
const authPanel = AuthPanel.create();
$("auth-panel").appendChild(authPanel.root);
let latest = null;
function showError(message) { $("error").textContent = message || "请求失败"; $("error").hidden = false; }
function render(payload) {
  latest = payload; const node = payload.node || {};
  $("title").textContent = payload.title || "表单流程";
  const process = payload.process; if (process) $("process-summary").textContent = `状态：${process.status} · 申请人：${process.applicant_id || "未指定"} · 审批人：${process.approver_id || "未分配"}`; $("description").textContent = payload.description || "";
  $("node-id").textContent = payload.node_id ? `NODE / ${payload.node_id}` : "FLOW COMPLETE"; $("node-title").textContent = node.title || "流程结束"; $("node-content").textContent = node.content || "";
  const form = $("request-form"); form.replaceChildren();
  if (payload.node_id === "draft") {
    (payload.fields || []).forEach((field) => { const label = document.createElement("label"); label.textContent = `${field.label}${field.required ? " *" : ""}`; const input = field.type === "textarea" ? document.createElement("textarea") : document.createElement("input"); input.name = field.key; input.type = field.type === "number" ? "number" : "text"; input.value = payload.form?.[field.key] ?? ""; label.appendChild(input); form.appendChild(label); });
    const submit = document.createElement("button"); submit.className = "submit"; submit.type = "submit"; submit.textContent = "保存并提交表单"; form.appendChild(submit); form.onsubmit = submitForm;
  }
  const transitions = $("transitions"); transitions.replaceChildren(); (node.transitions || []).forEach((transition, index) => { const button = document.createElement("button"); button.className = "transition"; button.type = "button"; button.textContent = transition.label || `转移 ${index + 1}`; button.onclick = () => advance(index); transitions.appendChild(button); });
  const history = payload.state?.records?.history || []; $("history").replaceChildren(); history.forEach((item) => { const li = document.createElement("li"); li.textContent = item; $("history").appendChild(li); });
  $("status").textContent = payload.form?.applicant ? `申请人：${payload.form.applicant}` : "尚未提交"; $("error").hidden = true;
}
async function submitForm(event) { event.preventDefault(); const values = Object.fromEntries(new FormData(event.target).entries()); try { const response = await fetch("/api/apps/request_form_demo/submit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) }); const payload = await response.json(); if (!response.ok) { showError(Object.values(payload.errors || {}).join("；") || payload.message); return; } render(payload); } catch (error) { showError(error.message); } }
async function advance(index) { try { const response = await fetch("/api/apps/request_form_demo/transition", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ index }) }); const payload = await response.json(); if (!response.ok || payload.success === false) throw Error(payload.message); render(payload); } catch (error) { showError(error.message); } }
$("reset").onclick = async () => { try { const response = await fetch("/api/apps/request_form_demo/reset", { method: "POST" }); render(await response.json()); } catch (error) { showError(error.message); } };
const savePanel = AppSavePanel.create({ appId: "request_form_demo", onState: render });
$("save-panel").appendChild(savePanel.root);
(async () => {
  try {
    await AppSavePanel.chooseResume({ appId: "request_form_demo", onState: render });
    const response = await fetch("/api/apps/request_form_demo/state");
    const payload = await response.json();
    if (!response.ok || payload.success === false) throw Error(payload.message);
    render(payload);
    await savePanel.refresh();
  } catch (error) { showError(error.message); }
})();
