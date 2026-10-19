"""应用运行时会话生命周期管理。"""
from typing import Any, Dict

from .app_registry import AppRegistry
from .runtime_protocol import ApplicationRuntime


class ApplicationSessionManager:
    """按应用 ID 和会话 ID 隔离协议兼容的运行时实例。"""

    def __init__(self, registry: AppRegistry, save_manager=None):
        self.registry = registry
        self.save_manager = save_manager
        self._sessions: Dict[tuple[str, str], ApplicationRuntime] = {}

    def set_save_manager(self, save_manager) -> None:
        self.save_manager = save_manager

    def get_or_create(self, app_id: str, session_id: str) -> ApplicationRuntime:
        key = (app_id, session_id)
        runtime = self._sessions.get(key)
        if runtime is None:
            runtime = self.registry.create_runtime(app_id)
            self._sessions[key] = runtime
            if self.save_manager is not None:
                self.save_manager.restore_current(app_id, session_id, runtime)
        return runtime

    def reset(self, app_id: str, session_id: str) -> ApplicationRuntime:
        self._sessions.pop((app_id, session_id), None)
        return self.get_or_create(app_id, session_id)

    def clear(self, app_id: str | None = None) -> None:
        if app_id is None:
            self._sessions.clear()
            return
        self._sessions = {
            key: runtime for key, runtime in self._sessions.items()
            if key[0] != app_id
        }

    def payload(self, app_id: str, session_id: str) -> Dict[str, Any]:
        runtime = self.get_or_create(app_id, session_id)
        return {
            "app_id": app_id,
            "app_type": runtime.definition.app_type,
            "title": runtime.definition.title,
            "description": runtime.definition.config.get("description", ""),
            **runtime.payload(),
        }

    def transition(self, app_id: str, session_id: str, index: int):
        return self.get_or_create(app_id, session_id).transition(index)

    def submit_form(self, app_id: str, session_id: str, values: dict) -> Dict[str, str]:
        runtime = self.get_or_create(app_id, session_id)
        submit = getattr(runtime, "submit_form", None)
        if not callable(submit):
            raise ValueError(f"application does not support form submission: {app_id}")
        return submit(values)
