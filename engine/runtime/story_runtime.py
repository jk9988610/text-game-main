"""互动故事到通用 FlowRuntime 的兼容适配器。"""
import json
from pathlib import Path
from typing import Any, Dict, Mapping

from .flow_runtime import FlowRuntime
from .runtime_definition import RuntimeDefinition


class InteractiveStoryRuntime:
    """保留旧 pages/choices 接口，同时由 FlowRuntime 执行实际逻辑。"""

    def __init__(self, definition: RuntimeDefinition,
                 pages: Mapping[str, Mapping[str, Any]]):
        if definition.app_type != "interactive_story":
            raise ValueError("definition must have app_type=interactive_story")
        self.definition = definition
        self.pages: Dict[str, Dict[str, Any]] = {
            str(key): dict(value) for key, value in pages.items()
        }
        self.flow = FlowRuntime(
            self._to_nodes(self.pages),
            definition.initial_page,
            definition.initial_state,
        )
        self.flow.state.set("current_page", definition.initial_page)
        self.state = self.flow.state
        self.actions = self.flow.actions
        self.validate()

    @classmethod
    def from_directory(cls, directory: str | Path) -> "InteractiveStoryRuntime":
        root = Path(directory)
        with (root / "app.json").open(encoding="utf-8") as handle:
            config = json.load(handle)
        with (root / "pages.json").open(encoding="utf-8") as handle:
            pages = json.load(handle)
        return cls(RuntimeDefinition(config, {"pages": pages}), pages)

    @staticmethod
    def _to_nodes(pages: Mapping[str, Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
        return {
            page_id: {
                "title": page.get("title", ""),
                "content": page.get("text", ""),
                "transitions": [
                    {
                        "label": choice.get("text", ""),
                        "to": choice.get("next"),
                        "if": choice.get("if"),
                        "actions": choice.get("actions", []),
                    }
                    for choice in page.get("choices", [])
                ],
            }
            for page_id, page in pages.items()
        }

    def validate(self) -> None:
        self.flow.validate()
        for page_id, page in self.pages.items():
            if not isinstance(page.get("text"), str):
                raise ValueError(f"page {page_id!r} must have text")

    def current_page(self) -> Dict[str, Any]:
        page_id = self.state.get("current_node")
        if page_id is None:
            return {}
        page = dict(self.pages[page_id])
        page["choices"] = []
        for transition in self.flow.current_node().get("transitions", []):
            choice = {"text": transition.get("label", ""),
                      "next": transition.get("to")}
            if transition.get("if") is not None:
                choice["if"] = transition["if"]
            if transition.get("actions"):
                choice["actions"] = transition["actions"]
            page["choices"].append(choice)
        return page

    def payload(self) -> Dict[str, Any]:
        return {
            "page_id": self.state.get("current_page"),
            "page": self.current_page(),
            "state": self.state.export(),
        }

    def choose(self, index: int) -> Dict[str, Any]:
        self.flow.transition(index)
        self.state.set("current_page", self.state.get("current_node"))
        return self.current_page()

    def transition(self, index: int) -> Dict[str, Any]:
        return self.choose(index)

    def validate_state(self, state: Mapping[str, Any]) -> None:
        page_id = state.get("current_page", state.get("current_node"))
        if page_id is not None and page_id not in self.pages:
            raise ValueError("存档页面已不存在")

