"""通用应用运行时基础组件。"""

from .action_registry import ActionContext, ActionRegistry
from .runtime_definition import RuntimeDefinition
from .runtime_state import RuntimeState
from .story_runtime import InteractiveStoryRuntime

__all__ = [
    "ActionContext",
    "ActionRegistry",
    "InteractiveStoryRuntime",
    "RuntimeDefinition",
    "RuntimeState",
]
