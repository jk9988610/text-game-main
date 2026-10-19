"""
文字游戏引擎包 —— 统一导出所有引擎模块
使用方式：from engine import EventBus, SceneManager, ItemSystem, ConsoleHandler, GameEvents
"""
from .event_bus import EventBus, GameEvents
from .scene_manager import SceneManager
from .item_system import ItemSystem
from .console_handler import ConsoleHandler
from .npc_system import NPCSystem
from .combat_system import CombatSystem
from .session_manager import SessionManager
from .save_manager import SaveManager
from .auth_manager import AuthManager
from .event_rules import DeclarativeRules
from . import beat_combat
from .organization_manager import OrganizationManager, ORG_LABELS
from .process_instance_manager import ProcessInstanceManager
from .role_manager import RoleManager, VALID_ROLES
from .runtime import (
    ActionContext,
    ActionRegistry,
    AppRegistry,
    ApplicationSaveManager,
    ApplicationSessionManager,
    RevisionConflictError,
    ApplicationRuntime,
    ConditionEvaluator,
    FlowRuntime,
    FormFlowRuntime,
    InteractiveStoryRuntime,
    RuntimeDefinition,
    RuntimeState,
    TaskFlowRuntime,
)

__all__ = [
    "EventBus",
    "GameEvents",
    "SceneManager",
    "ItemSystem",
    "ConsoleHandler",
    "NPCSystem",
    "CombatSystem",
    "SessionManager",
    "SaveManager",
    "AuthManager",
    "DeclarativeRules",
    "beat_combat",
    "RoleManager",
    "VALID_ROLES",
    "ProcessInstanceManager",
    "OrganizationManager",
    "ORG_LABELS",
    "ActionContext",
    "ActionRegistry",
    "AppRegistry",
    "ApplicationSaveManager",
    "ApplicationSessionManager",
    "RevisionConflictError",
    "ApplicationRuntime",
    "ConditionEvaluator",
    "FlowRuntime",
    "FormFlowRuntime",
    "InteractiveStoryRuntime",
    "RuntimeDefinition",
    "RuntimeState",
    "TaskFlowRuntime",
]
