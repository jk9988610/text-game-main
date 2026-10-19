"""表单流程运行时适配器。"""
import json
from pathlib import Path
from typing import Any, Dict, Mapping

from .flow_runtime import FlowRuntime
from .runtime_definition import RuntimeDefinition


class FormFlowRuntime:
    """在 FlowRuntime 上增加表单字段校验和提交能力。"""

    def __init__(self, definition: RuntimeDefinition,
                 fields: list[Mapping[str, Any]],
                 nodes: Dict[str, Dict[str, Any]]):
        if definition.app_type != "form_flow":
            raise ValueError("definition must have app_type=form_flow")
        self.definition = definition
        self.fields = [dict(field) for field in fields]
        self.flow = FlowRuntime(
            nodes,
            definition.initial_page,
            definition.initial_state,
        )

    @classmethod
    def from_directory(cls, directory: str | Path) -> "FormFlowRuntime":
        root = Path(directory)
        with (root / "app.json").open(encoding="utf-8") as handle:
            config = json.load(handle)
        with (root / "form.json").open(encoding="utf-8") as handle:
            form = json.load(handle)
        with (root / "nodes.json").open(encoding="utf-8") as handle:
            nodes = json.load(handle)
        return cls(
            RuntimeDefinition(config, {"nodes": nodes, "form": form}),
            form.get("fields", []),
            nodes,
        )

    @property
    def state(self):
        return self.flow.state

    def current_node(self) -> Dict[str, Any]:
        return self.flow.current_node()

    def validate_form(self, values: Mapping[str, Any]) -> Dict[str, str]:
        if not isinstance(values, Mapping):
            return {"form": "表单数据必须是对象"}
        errors: Dict[str, str] = {}
        for field in self.fields:
            key = field.get("key")
            value = values.get(key)
            label = field.get("label", key)
            if field.get("required") and (value is None or str(value).strip() == ""):
                errors[key] = f"{label}不能为空"
                continue
            if field.get("type") == "number" and value not in (None, ""):
                try:
                    number = float(value)
                    if "min" in field and number < field["min"]:
                        errors[key] = f"{label}不能小于 {field['min']}"
                except (TypeError, ValueError):
                    errors[key] = f"{label}必须是数字"
        return errors

    def submit_form(self, values: Mapping[str, Any]) -> Dict[str, str]:
        errors = self.validate_form(values)
        if errors:
            return errors
        normalized = dict(values)
        for field in self.fields:
            key = field.get("key")
            if field.get("type") == "number" and normalized.get(key) not in (None, ""):
                normalized[key] = float(normalized[key])
        self.state.set("variables.form", normalized)
        return {}

    def has_submitted_form(self) -> bool:
        values = self.state.get("variables.form", {})
        return isinstance(values, dict) and all(
            not field.get("required") or values.get(field.get("key")) not in (None, "")
            for field in self.fields
        )

    def advance(self, index: int) -> Dict[str, Any]:
        return self.flow.transition(index)

    def payload(self) -> Dict[str, Any]:
        return {
            "node_id": self.state.get("current_node"),
            "node": self.current_node(),
            "fields": [dict(field) for field in self.fields],
            "form": self.state.get("variables.form", {}),
            "state": self.state.export(),
        }

    def transition(self, index: int) -> Dict[str, Any]:
        if self.state.get("current_node") == "draft" and not self.has_submitted_form():
            raise ValueError("请先完整提交表单")
        return self.advance(index)

    def validate_state(self, state: Mapping[str, Any]) -> None:
        node_id = state.get("current_node", state.get("current_page"))
        if node_id is not None and node_id not in self.flow.nodes:
            raise ValueError("存档节点已不存在")
