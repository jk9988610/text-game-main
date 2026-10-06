const $ = (id) => document.getElementById(id);
const model = { config: null, pages: {}, selected: null };

function notice(message, error = false) {
  const node = $("notice");
  node.textContent = message;
  node.style.background = error ? "#3a2424" : "#29332b";
  node.style.color = error ? "#ffc4c4" : "#c4efc8";
  node.classList.add("show");
  window.clearTimeout(notice.timer);
  notice.timer = window.setTimeout(() => node.classList.remove("show"), 2600);
}

function currentPage() { return model.pages[model.selected]; }
function updateModel() {
  const page = currentPage();
  if (!page) return;
  page.title = $("page-title").value;
  page.text = $("page-text").value;
  model.config.title = $("story-title").value;
  model.config.description = $("story-description").value;
  model.config.initial_page = $("initial-page").value;
}

function renderPageList() {
  const list = $("page-list");
  list.replaceChildren();
  const ids = Object.keys(model.pages);
  $("page-count").textContent = `${ids.length} 页`;
  ids.forEach((id) => {
    const page = model.pages[id];
    const button = document.createElement("button");
    button.className = `page-item${id === model.selected ? " active" : ""}`;
    button.innerHTML = `${escapeHtml(page.title || id)}<small>${escapeHtml(id)}</small>`;
    button.addEventListener("click", () => { updateModel(); model.selected = id; render(); });
    list.appendChild(button);
  });
}

function renderInitialPageOptions() {
  const select = $("initial-page");
  select.replaceChildren();
  Object.keys(model.pages).forEach((id) => {
    const option = document.createElement("option");
    option.value = id; option.textContent = `${id} · ${model.pages[id].title || "未命名"}`;
    select.appendChild(option);
  });
  select.value = model.config.initial_page;
}

function renderChoices() {
  const page = currentPage();
  const box = $("choices");
  box.replaceChildren();
  const choices = page.choices || [];
  $("empty-choices").hidden = choices.length > 0;
  choices.forEach((choice, index) => {
    const card = document.createElement("div");
    card.className = "choice-card";
    card.innerHTML = `<div class="choice-card-head"><span>选项 ${index + 1}</span><button class="remove-choice" type="button">删除</button></div><label>文字<textarea class="choice-text" rows="2"></textarea></label><label>跳转到<select class="choice-next"></select></label><div class="logic-grid"><label>条件路径<input class="choice-if-path" placeholder="如 variables.has_key"></label><label>运算<select class="choice-if-op"><option value="equals">等于</option><option value="not_equals">不等于</option><option value="greater_than">大于</option><option value="greater_or_equal">大于等于</option><option value="less_than">小于</option><option value="less_or_equal">小于等于</option><option value="truthy">为真</option><option value="falsy">为假</option></select></label><label>条件值<input class="choice-if-value" placeholder="true / 1 / 文本"></label></div><div class="action-box"><strong>动作</strong><select class="action-type"><option value="">无动作</option><option value="set_variable">设置变量</option><option value="modify_variable">修改数值</option></select><input class="action-path" placeholder="变量路径，如 variables.trust"><input class="action-value" placeholder="值或增量"></div>`;
    card.querySelector(".choice-text").value = choice.text || "";
    const select = card.querySelector(".choice-next");
    const end = document.createElement("option"); end.value = ""; end.textContent = "故事结束"; select.appendChild(end);
    Object.keys(model.pages).forEach((id) => { const option = document.createElement("option"); option.value = id; option.textContent = id; select.appendChild(option); });
    select.value = choice.next || "";
    const condition = choice.if || {};
    card.querySelector(".choice-if-path").value = condition.path || "";
    card.querySelector(".choice-if-op").value = condition.operator || "equals";
    card.querySelector(".choice-if-value").value = condition.value ?? "";
    const action = (choice.actions || [])[0] || {};
    card.querySelector(".action-type").value = action.type || "";
    card.querySelector(".action-path").value = action.path || "";
    card.querySelector(".action-value").value = action.value ?? action.amount ?? "";
    card.querySelector(".choice-text").addEventListener("input", (event) => { choice.text = event.target.value; });
    select.addEventListener("change", (event) => { choice.next = event.target.value || null; });
    const syncLogic = () => {
      const path = card.querySelector(".choice-if-path").value.trim();
      if (!path) delete choice.if;
      else {
        const raw = card.querySelector(".choice-if-value").value;
        const value = raw === "true" ? true : raw === "false" ? false : (raw !== "" && !Number.isNaN(Number(raw)) ? Number(raw) : raw);
        choice.if = { path, operator: card.querySelector(".choice-if-op").value, value };
      }
      const type = card.querySelector(".action-type").value;
      if (!type) delete choice.actions;
      else {
        const action = { type, path: card.querySelector(".action-path").value.trim() };
        const raw = card.querySelector(".action-value").value;
        if (type === "set_variable") action.value = raw === "true" ? true : raw === "false" ? false : raw;
        else action.amount = Number(raw);
        choice.actions = [action];
      }
    };
    card.querySelectorAll(".choice-if-path, .choice-if-op, .choice-if-value, .action-type, .action-path, .action-value").forEach((node) => node.addEventListener("input", syncLogic));
    card.querySelectorAll("select").forEach((node) => node.addEventListener("change", syncLogic));
    card.querySelector(".remove-choice").addEventListener("click", () => { page.choices.splice(index, 1); renderChoices(); });
    box.appendChild(card);
  });
}

function render() {
  renderPageList(); renderInitialPageOptions();
  $("story-title").value = model.config.title || "";
  $("story-description").value = model.config.description || "";
  const page = currentPage();
  $("page-id").value = model.selected || "";
  $("page-title").value = page?.title || "";
  $("page-text").value = page?.text || "";
  $("delete-page").disabled = Object.keys(model.pages).length <= 1;
  renderChoices();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
}

$("add-page").addEventListener("click", () => {
  updateModel();
  let id = "new_page", count = 2;
  while (model.pages[id]) id = `new_page_${count++}`;
  model.pages[id] = { title: "新页面", text: "", choices: [] };
  model.selected = id; render();
});
$("delete-page").addEventListener("click", () => {
  if (Object.keys(model.pages).length <= 1) return;
  const id = model.selected;
  if (!window.confirm(`删除页面 ${id}？相关选项会变成故事结束。`)) return;
  delete model.pages[id];
  Object.values(model.pages).forEach((page) => (page.choices || []).forEach((choice) => { if (choice.next === id) choice.next = null; }));
  if (model.config.initial_page === id) model.config.initial_page = Object.keys(model.pages)[0];
  model.selected = Object.keys(model.pages)[0]; render();
});
$("add-choice").addEventListener("click", () => { updateModel(); currentPage().choices = currentPage().choices || []; currentPage().choices.push({ text: "新选项", next: null }); renderChoices(); });
$("page-title").addEventListener("input", updateModel);
$("page-text").addEventListener("input", updateModel);
$("story-title").addEventListener("input", updateModel);
$("story-description").addEventListener("input", updateModel);
$("initial-page").addEventListener("change", updateModel);
$("save").addEventListener("click", async () => {
  updateModel();
  try {
    const response = await fetch("/api/story/editor/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ config: model.config, pages: model.pages }) });
    const payload = await response.json();
    if (!response.ok || payload.success === false) throw new Error(payload.message);
    notice(payload.message || "已保存");
  } catch (error) { notice(error.message, true); }
});

fetch("/api/story/editor/data").then((response) => response.json()).then((payload) => {
  if (!payload.success) throw new Error(payload.message);
  model.config = payload.config; model.pages = payload.pages; model.selected = model.config.initial_page || Object.keys(model.pages)[0]; render();
}).catch((error) => notice(error.message, true));
