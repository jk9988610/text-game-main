const $ = (id) => document.getElementById(id);
const authPanel = AuthPanel.create();
$("auth-panel").appendChild(authPanel.root);

function showError(message) {
  const node = $("story-error");
  node.textContent = message || "请求失败";
  node.hidden = false;
}

function render(payload) {
  $("story-title").textContent = payload.title || "互动故事";
  $("story-description").textContent = payload.description || "";
  const page = payload.page || {};
  $("page-kicker").textContent = payload.page_id ? `PAGE / ${payload.page_id}` : "STORY COMPLETE";
  $("page-title").textContent = page.title || "故事结束";
  $("page-text").textContent = page.text || "这段故事已经结束。";
  const choices = $("choices");
  choices.replaceChildren();
  (page.choices || []).forEach((choice, index) => {
    const button = document.createElement("button");
    button.className = "choice";
    button.type = "button";
    button.textContent = choice.text || `选择 ${index + 1}`;
    button.addEventListener("click", () => choose(index));
    choices.appendChild(button);
  });
  const trust = payload.state?.variables?.trust;
  $("state-summary").textContent = typeof trust === "number" ? `信任值 ${trust}` : "故事状态已保存";
  $("story-error").hidden = true;
}

async function loadState() {
  const response = await fetch("/api/apps/first_branch/state");
  const payload = await response.json();
  if (!response.ok || payload.success === false) throw new Error(payload.message);
  render(payload);
}

async function choose(index) {
  document.querySelectorAll(".choice").forEach((button) => { button.disabled = true; });
  try {
    const response = await fetch("/api/apps/first_branch/transition", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index }),
    });
    const payload = await response.json();
    if (!response.ok || payload.success === false) throw new Error(payload.message);
    render(payload);
  } catch (error) {
    showError(error.message);
    document.querySelectorAll(".choice").forEach((button) => { button.disabled = false; });
  }
}

$("restart").addEventListener("click", async () => {
  try {
    const response = await fetch("/api/apps/first_branch/reset", { method: "POST" });
    const payload = await response.json();
    if (!response.ok || payload.success === false) throw new Error(payload.message);
    render(payload);
  } catch (error) {
    showError(error.message);
  }
});

const savePanel = AppSavePanel.create({ appId: "first_branch", onState: render });
$("save-panel").appendChild(savePanel.root);
(async () => {
  try {
    await AppSavePanel.chooseResume({ appId: "first_branch", onState: render });
    await loadState();
    await savePanel.refresh();
  } catch (error) { showError(error.message); }
})();
