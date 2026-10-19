"""通用应用运行时基础组件。"""

from .action_registry import ActionContext, ActionRegistry
from .app_registry import AppRegistry
from .app_session_manager import ApplicationSessionManager
from .application_save_manager import ApplicationSaveManager, RevisionConflictError
from .condition_evaluator import ConditionEvaluator
from .flow_runtime import FlowRuntime
from .form_runtime import FormFlowRuntime
from .runtime_definition import RuntimeDefinition
from .runtime_protocol import ApplicationRuntime
from .runtime_state import RuntimeState
from .story_runtime import InteractiveStoryRuntime
from .task_runtime import TaskFlowRuntime

__all__ = [
    "ActionContext",
    "ActionRegistry",
    "ApplicationRuntime",
    "AppRegistry",
    "ApplicationSaveManager",
    "ApplicationSessionManager",
    "RevisionConflictError",
    "ConditionEvaluator",
    "FlowRuntime",
    "FormFlowRuntime",
    "InteractiveStoryRuntime",
    "RuntimeDefinition",
    "RuntimeState",
    "TaskFlowRuntime",
]
