"""最小互动故事运行时适配器。"""
import json
from pathlib import Path
from typing import Any, Dict, Mapping

from .action_registry import ActionContext, ActionRegistry
from .runtime_definition import RuntimeDefinition
from .runtime_state import RuntimeState


class InteractiveStoryRuntime:
    """将互动故事页面适配到通用 RuntimeState 和 ActionRegistry。"""

    def __init__(self, definition: RuntimeDefinition,
                 pages: Mapping[str, Mapping[str, Any]]):
        if definition.app_type != "interactive_story":
            raise ValueError("definition must have app_type=interactive_story")
        self.definition = definition
        self.pages: Dict[str, Dict[str, Any]] = {
            str(key): dict(value) for key, value in pages.items()
        }
        self.state = RuntimeState(definition.initial_state)
        self.state.set("current_page", definition.initial_page)
        self.actions = ActionRegistry()
        self.actions.register("set_variable", self._set_variable)
        self.actions.register("modify_variable", self._modify_variable)
        self.validate()

    @classmethod
    def from_directory(cls, directory: str | Path) -> "InteractiveStoryRuntime":
        root = Path(directory)
        with (root / "app.json").open(encoding="utf-8") as handle:
            config = json.load(handle)
        with (root / "pages.json").open(encoding="utf-8") as handle:
            pages = json.load(handle)
        return cls(RuntimeDefinition(config, {"pages": pages}), pages)

    def validate(self) -> None:
        initial = self.definition.initial_page
        if initial not in self.pages:
            raise ValueError(f"initial page does not exist: {initial!r}")
        for page_id, page in self.pages.items():
            if not isinstance(page.get("text"), str):
                raise ValueError(f"page {page_id!r} must have text")
            for choice in page.get("choices", []):
                target = choice.get("next")
                if target is not None and target not in self.pages:
                    raise ValueError(
                        f"choice from {page_id!r} points to missing page {target!r}"
                    )

    def current_page(self) -> Dict[str, Any]:
        page_id = self.state.get("current_page")
        return dict(self.pages[page_id])

    def choose(self, index: int) -> Dict[str, Any]:
        page = self.current_page()
        choices = page.get("choices", [])
        if not isinstance(index, int) or index < 0 or index >= len(choices):
            raise IndexError("choice index out of range")
        choice = choices[index]
        context = ActionContext(self.state, {"pages": self.pages})
        self.actions.execute_many(choice.get("actions", []), context)
        self.state.set("current_page", choice.get("next"))
        return self.current_page() if choice.get("next") is not None else {}

    @staticmethod
    def _set_variable(context: ActionContext, action: Dict[str, Any]) -> Any:
        return context.state.set(action["path"], action.get("value"))

    @staticmethod
    def _modify_variable(context: ActionContext, action: Dict[str, Any]) -> Any:
        return context.state.update(action["path"], action["amount"])
