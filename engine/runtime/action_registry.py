"""可扩展的通用动作注册表。"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping

from .runtime_state import RuntimeState

ActionHandler = Callable[["ActionContext", Dict[str, Any]], Any]


@dataclass
class ActionContext:
    """动作执行时可用的运行时上下文。"""

    state: RuntimeState
    data: Mapping[str, Any] = field(default_factory=dict)
    results: list[Any] = field(default_factory=list)


class ActionRegistry:
    """将动作名称映射到处理函数。

    处理函数签名为 ``handler(context, action)``，其中 action 至少包含
    ``type`` 字段。注册表本身不依赖 Flask 或具体游戏模块。
    """

    def __init__(self):
        self._handlers: Dict[str, ActionHandler] = {}

    def register(self, name: str, handler: ActionHandler, *, replace: bool = False) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("action name must be a non-empty string")
        if not callable(handler):
            raise TypeError("action handler must be callable")
        if name in self._handlers and not replace:
            raise ValueError(f"action already registered: {name}")
        self._handlers[name] = handler

    def register_many(self, handlers: Mapping[str, ActionHandler], *, replace: bool = False) -> None:
        for name, handler in handlers.items():
            self.register(name, handler, replace=replace)

    def execute(self, action: Mapping[str, Any], context: ActionContext) -> Any:
        if not isinstance(action, Mapping):
            raise TypeError("action must be a mapping")
        if not isinstance(context, ActionContext):
            raise TypeError("context must be an ActionContext")
        name = action.get("type")
        handler = self._handlers.get(name)
        if handler is None:
            raise KeyError(f"unknown action type: {name!r}")
        return handler(context, dict(action))

    def execute_many(self, actions: list[Mapping[str, Any]], context: ActionContext) -> list[Any]:
        results = [self.execute(action, context) for action in actions]
        context.results.extend(results)
        return results

    def has(self, name: str) -> bool:
        return name in self._handlers

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))
