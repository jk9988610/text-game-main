/* 三种应用共用的存档面板和启动恢复流程。 */
window.AppSavePanel = (() => {
  function create(options) {
    const root = document.createElement("section");
    root.className = "save-panel";
    root.innerHTML = `<div class="save-panel-head"><strong>进度</strong><span class="save-status"></span></div><div class="save-panel-actions"><input class="save-slot" value="manual" maxlength="32" aria-label="存档槽位"><button class="save-button" type="button">保存</button><button class="load-button" type="button">读取</button><button class="delete-button" type="button">删除</button><button class="refresh-button" type="button">刷新</button></div><div class="save-list"></div>`;
    const status = root.querySelector(".save-status");
    const list = root.querySelector(".save-list");
    const slot = root.querySelector(".save-slot");
    const request = (path, init = {}) => fetch(`/api/apps/${encodeURIComponent(options.appId)}${path}`, init).then(async (response) => { const payload = await response.json(); if (!response.ok || payload.success === false) throw new Error(payload.message || Object.values(payload.errors || {}).join("；") || "存档请求失败"); return payload; });
    const setStatus = (message, error = false) => { status.textContent = message; status.dataset.error = error ? "true" : "false"; };
    function renderSaves(saves) { list.replaceChildren(); saves.forEach((save) => { const button = document.createElement("button"); button.type = "button"; button.className = "save-item"; button.textContent = `${save.slot_name.replace(/^app:[^:]+:/, "")} · ${save.updated_at}`; button.onclick = () => { slot.value = save.slot_name.replace(/^app:[^:]+:/, ""); }; list.appendChild(button); }); }
    async function refresh() { const payload = await request("/saves"); renderSaves(payload.saves || []); return payload; }
    async function save() { setStatus("保存中…"); try { await request("/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slot: slot.value || "manual" }) }); await refresh(); setStatus("已保存"); } catch (error) { setStatus(error.message, true); } }
    async function load() { setStatus("读取中…"); try { const payload = await request("/load", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slot: slot.value || "auto" }) }); setStatus("已读取"); options.onState?.(payload); } catch (error) { setStatus(error.message, true); } }
    async function remove() { setStatus("删除中…"); try { await request("/delete-save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slot: slot.value || "manual" }) }); await refresh(); setStatus("已删除"); } catch (error) { setStatus(error.message, true); } }
    root.querySelector(".save-button").onclick = save; root.querySelector(".load-button").onclick = load; root.querySelector(".delete-button").onclick = remove; root.querySelector(".refresh-button").onclick = () => refresh().catch((error) => setStatus(error.message, true));
    return { root, refresh, save, load, setStatus };
  }
  async function chooseResume(options) { const request = (path, init = {}) => fetch(`/api/apps/${encodeURIComponent(options.appId)}${path}`, init).then((response) => response.json()); const saves = await request("/saves"); const hasAuto = (saves.saves || []).some((save) => save.slot_name.endsWith(":auto")); if (!hasAuto) return "new"; const resume = window.confirm("发现上次自动保存的进度。点击“确定”继续，点击“取消”重新开始。"); if (resume) { const payload = await request("/load", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slot: "auto" }) }); options.onState?.(payload); return "resume"; } await request("/reset", { method: "POST" }); return "new"; }
  return { create, chooseResume };
})();
