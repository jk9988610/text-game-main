/* 两种流程编辑器共享的纯前端工具。 */
window.FlowEditorCore = (() => {
  function uniqueId(collection, prefix) {
    let id = prefix;
    let index = 2;
    while (Object.prototype.hasOwnProperty.call(collection, id)) {
      id = `${prefix}_${index++}`;
    }
    return id;
  }

  function parseScalar(raw) {
    const value = String(raw ?? "");
    if (value === "true") return true;
    if (value === "false") return false;
    if (value !== "" && !Number.isNaN(Number(value))) return Number(value);
    return value;
  }

  function removeNodeReferences(nodes, removedId) {
    Object.values(nodes).forEach((node) => {
      (node.transitions || []).forEach((transition) => {
        if (transition.to === removedId) transition.to = null;
      });
      (node.choices || []).forEach((choice) => {
        if (choice.next === removedId) choice.next = null;
      });
    });
  }

  async function requestJSON(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json();
    if (!response.ok || payload.success === false) {
      throw new Error(payload.message || `请求失败（${response.status}）`);
    }
    return payload;
  }

  return { uniqueId, parseScalar, removeNodeReferences, requestJSON };
})();
