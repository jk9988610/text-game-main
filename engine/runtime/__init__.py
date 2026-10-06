"""通用应用运行时基础组件。"""

from .action_registry import ActionContext, ActionRegistry
from .runtime_definition import RuntimeDefinition
from .runtime_state import RuntimeState

__all__ = [
    "ActionContext",
    "ActionRegistry",
    "RuntimeDefinition",
    "RuntimeState",
]
