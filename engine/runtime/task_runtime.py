"""任务流程模板适配器。"""
import json
from pathlib import Path
from typing import Any, Dict

from .flow_runtime import FlowRuntime
from .runtime_definition import RuntimeDefinition


class TaskFlowRuntime:
    """将任务流程模板接入通用 FlowRuntime。"""

    def __init__(self, definition: RuntimeDefinition,
                 nodes: Dict[str, Dict[str, Any]]):
        if definition.app_type != "task_flow":
            raise ValueError("definition must have app_type=task_flow")
        self.definition = definition
        self.flow = FlowRuntime(
            nodes,
            definition.initial_page,
            definition.initial_state,
        )

    @classmethod
    def from_directory(cls, directory: str | Path) -> "TaskFlowRuntime":
        root = Path(directory)
        with (root / "app.json").open(encoding="utf-8") as handle:
            config = json.load(handle)
        with (root / "nodes.json").open(encoding="utf-8") as handle:
            nodes = json.load(handle)
        return cls(RuntimeDefinition(config, {"nodes": nodes}), nodes)

    @property
    def state(self):
        return self.flow.state

    def current_node(self) -> Dict[str, Any]:
        return self.flow.current_node()

    def current_task(self) -> Dict[str, Any]:
        return self.current_node()

    def advance(self, index: int) -> Dict[str, Any]:
        return self.flow.transition(index)

    def payload(self) -> Dict[str, Any]:
        return {
            "node_id": self.state.get("current_node"),
            "node": self.current_node(),
            "state": self.state.export(),
        }

    def transition(self, index: int) -> Dict[str, Any]:
        return self.advance(index)

    def validate_state(self, state: Dict[str, Any]) -> None:
        node_id = state.get("current_node", state.get("current_page"))
        if node_id is not None and node_id not in self.flow.nodes:
            raise ValueError("存档节点已不存在")
