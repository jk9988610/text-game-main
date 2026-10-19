const authPanel = AuthPanel.create({ onChange: updateEditorPermission });
document.getElementById("auth-panel").appendChild(authPanel.root);
function updateEditorPermission(context) {
  const save = document.getElementById("save");
  if (!save) return;
  const allowed = context.demo || (context.roles || []).includes("admin");
  save.disabled = !allowed;
  save.title = allowed ? "" : "需要管理员角色才能保存模板";
}
const $ = (id) => document.getElementById(id);
const model = { config: null, nodes: {}, selected: null };
function say(text, error = false) {
  const node = $("notice"); node.textContent = text;
  node.style.background = error ? "#3a2424" : "#29332b";
  node.classList.add("show"); clearTimeout(say.timer);
  say.timer = setTimeout(() => node.classList.remove("show"), 2500);
}
function current() { return model.nodes[model.selected]; }
function sync() {
  const node = current(); if (!node) return;
  node.title = $("node-title").value; node.content = $("node-content").value;
  model.config.title = $("flow-title").value;
  model.config.description = $("flow-description").value;
  model.config.initial_page = $("initial-node").value;
}
function renderTransitions() {
  const list = current().transitions || []; const box = $("transitions"); box.replaceChildren();
  $("empty").hidden = list.length > 0;
  list.forEach((transition, index) => {
    const card = document.createElement("div"); card.className = "transition-card";
    card.innerHTML = `<div class="transition-head"><span>转移 ${index + 1}</span><button class="remove" type="button">删除</button></div><label>名称<input class="label"></label><label>目标节点<select class="target"></select></label>`;
    card.querySelector(".label").value = transition.label || "";
    card.querySelector(".label").oninput = (event) => { transition.label = event.target.value; };
    const select = card.querySelector(".target");
    Object.keys(model.nodes).forEach((id) => { const option = document.createElement("option"); option.value = id; option.textContent = id; select.appendChild(option); });
    select.value = transition.to || ""; select.onchange = (event) => { transition.to = event.target.value; };
    card.querySelector(".remove").onclick = () => { list.splice(index, 1); renderTransitions(); };
    box.appendChild(card);
  });
}
function render() {
  const ids = Object.keys(model.nodes); $("count").textContent = `${ids.length} 个`;
  const list = $("node-list"); list.replaceChildren();
  ids.forEach((id) => { const button = document.createElement("button"); button.className = `node-button${id === model.selected ? " active" : ""}`; button.textContent = model.nodes[id].title || id; const small = document.createElement("small"); small.textContent = id; button.appendChild(small); button.onclick = () => { sync(); model.selected = id; render(); }; list.appendChild(button); });
  const select = $("initial-node"); select.replaceChildren(); ids.forEach((id) => { const option = document.createElement("option"); option.value = id; option.textContent = id; select.appendChild(option); }); select.value = model.config.initial_page;
  $("flow-title").value = model.config.title || ""; $("flow-description").value = model.config.description || "";
  const node = current(); $("node-id").value = model.selected; $("node-title").value = node.title || ""; $("node-content").value = node.content || ""; $("delete-node").disabled = ids.length <= 1; renderTransitions();
}
$("add-node").onclick = () => { sync(); const id = FlowEditorCore.uniqueId(model.nodes, "new_node"); model.nodes[id] = { title: "新节点", content: "", transitions: [] }; model.selected = id; render(); };
$("delete-node").onclick = () => { if (Object.keys(model.nodes).length <= 1) return; if (!confirm(`删除节点 ${model.selected}？`)) return; const id = model.selected; delete model.nodes[id]; FlowEditorCore.removeNodeReferences(model.nodes, id); model.config.initial_page = Object.keys(model.nodes)[0]; model.selected = model.config.initial_page; render(); };
$("add-transition").onclick = () => { sync(); current().transitions.push({ label: "新转移", to: Object.keys(model.nodes)[0] }); renderTransitions(); };
["flow-title", "flow-description", "node-title", "node-content", "initial-node"].forEach((id) => $(id).addEventListener("input", sync)); $("initial-node").addEventListener("change", sync);
$("save").onclick = async () => { sync(); try { const payload = await FlowEditorCore.requestJSON("/api/task/editor/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ config: model.config, nodes: model.nodes }) }); say(payload.message); } catch (error) { say(error.message, true); } };
fetch("/api/task/editor/data").then((response) => response.json()).then((payload) => { if (!payload.success) throw Error(payload.message); model.config = payload.config; model.nodes = payload.nodes; model.selected = payload.config.initial_page || Object.keys(payload.nodes)[0]; render(); }).catch((error) => say(error.message, true));
