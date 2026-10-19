"""通用节点流程运行时。"""
from typing import Any, Dict, Mapping

from .action_registry import ActionContext, ActionRegistry
from .condition_evaluator import ConditionEvaluator
from .runtime_state import RuntimeState


class FlowRuntime:
    """执行节点、转移、条件和动作组成的声明式流程。

    节点格式：
    ``{"title": ..., "content": ..., "transitions": [...]}``
    转移格式：
    ``{"label": ..., "to": "node_id", "if": {...}, "actions": [...]}``
    """

    def __init__(self, nodes: Mapping[str, Mapping[str, Any]], initial_node: str,
                 initial_state: Mapping[str, Any] | None = None,
                 actions: ActionRegistry | None = None):
        self.nodes: Dict[str, Dict[str, Any]] = {
            str(key): dict(value) for key, value in nodes.items()
        }
        self.state = RuntimeState(initial_state)
        self.state.set("current_node", initial_node)
        self.actions = actions or ActionRegistry()
        if not self.actions.has("set_variable"):
            self.actions.register("set_variable", self._set_variable)
        if not self.actions.has("modify_variable"):
            self.actions.register("modify_variable", self._modify_variable)
        if not self.actions.has("append_record"):
            self.actions.register("append_record", self._append_record)
        if not self.actions.has("show_message"):
            self.actions.register("show_message", self._show_message)
        self.validate()

    def validate(self) -> None:
        initial = self.state.get("current_node")
        if initial not in self.nodes:
            raise ValueError(f"initial node does not exist: {initial!r}")
        for node_id, node in self.nodes.items():
            for transition in node.get("transitions", []):
                target = transition.get("to")
                if target is not None and target not in self.nodes:
                    raise ValueError(
                        f"transition from {node_id!r} points to missing node {target!r}"
                    )

    def current_node(self) -> Dict[str, Any]:
        node_id = self.state.get("current_node")
        if node_id is None:
            return {}
        node = dict(self.nodes[node_id])
        node["transitions"] = [
            transition for transition in node.get("transitions", [])
            if ConditionEvaluator(self.state).matches(transition.get("if"))
        ]
        return node

    def transition(self, index: int) -> Dict[str, Any]:
        transitions = self.current_node().get("transitions", [])
        if not isinstance(index, int) or index < 0 or index >= len(transitions):
            raise IndexError("transition index out of range")
        selected = transitions[index]
        context = ActionContext(self.state, {"nodes": self.nodes})
        self.actions.execute_many(selected.get("actions", []), context)
        self.state.set("current_node", selected.get("to"))
        return self.current_node()

    @staticmethod
    def _set_variable(context: ActionContext, action: Dict[str, Any]) -> Any:
        return context.state.set(action["path"], action.get("value"))

    @staticmethod
    def _modify_variable(context: ActionContext, action: Dict[str, Any]) -> Any:
        return context.state.update(action["path"], action["amount"])

    @staticmethod
    def _append_record(context: ActionContext, action: Dict[str, Any]) -> Any:
        path = action.get("path", "records.entries")
        records = context.state.get(path, [])
        if not isinstance(records, list):
            raise TypeError(f"record collection at {path!r} is not a list")
        records = list(records)
        records.append(action.get("value"))
        return context.state.set(path, records)

    @staticmethod
    def _show_message(context: ActionContext, action: Dict[str, Any]) -> Any:
        message = str(action.get("message", ""))
        context.results.append(message)
        return message
