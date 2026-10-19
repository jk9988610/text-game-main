"""统一应用存档管理。"""
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict

from ..save_manager import SaveManager
from .app_registry import AppRegistry
from .app_session_manager import ApplicationSessionManager


class RevisionConflictError(ValueError):
    """客户端基于旧版本保存时抛出。"""


class ApplicationSaveManager:
    """为所有注册应用提供版本化、隔离的槽位和当前状态存储。"""

    SCHEMA_VERSION = 1
    CURRENT_SLOT = "__current__"

    def __init__(self, registry: AppRegistry,
                 sessions: ApplicationSessionManager,
                 db_path: str = "game_data/application_saves.db"):
        self.registry = registry
        self.sessions = sessions
        self.store = SaveManager(db_path=db_path, defaults={})
        self.sessions.set_save_manager(self)

    @staticmethod
    def _key(app_id: str, slot: str) -> str:
        return f"app:{app_id}:{slot}"

    def _read(self, app_id: str, session_id: str, slot: str):
        return self.store.load_slot(session_id, self._key(app_id, slot))

    def _save_state(self, app_id: str, session_id: str, slot: str,
                    *, expected_revision: int | None = None) -> Dict[str, Any]:
        runtime = self.sessions.get_or_create(app_id, session_id)
        previous = self._read(app_id, session_id, slot)
        current_revision = int((previous or {}).get("revision", 0))
        if expected_revision is not None and expected_revision != current_revision:
            raise RevisionConflictError(
                f"存档版本冲突：当前为 {current_revision}，提交的是 {expected_revision}"
            )
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "schema_version": self.SCHEMA_VERSION,
            "app_id": app_id,
            "app_type": runtime.definition.app_type,
            "revision": current_revision + 1,
            "updated_at": now,
            "state": runtime.state.export(),
        }
        result = self.store.save_slot(
            session_id, self._key(app_id, slot), data, is_auto=slot == "auto"
        )
        return {"slot": slot, "revision": data["revision"],
                "updated_at": now, **result}

    def save(self, app_id: str, session_id: str, slot: str = "auto",
             expected_revision: int | None = None) -> Dict[str, Any]:
        self._validate_slot(slot)
        return self._save_state(app_id, session_id, slot,
                                expected_revision=expected_revision)

    def save_current(self, app_id: str, session_id: str) -> Dict[str, Any]:
        return self._save_state(app_id, session_id, self.CURRENT_SLOT)

    def restore_current(self, app_id: str, session_id: str, runtime=None) -> bool:
        saved = self._read(app_id, session_id, self.CURRENT_SLOT)
        if not saved:
            return False
        self._restore(app_id, session_id, saved, runtime)
        return True

    def _restore(self, app_id: str, session_id: str, saved: Dict[str, Any], runtime=None) -> None:
        runtime = runtime or self.sessions.get_or_create(app_id, session_id)
        if saved.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError("不支持的存档版本")
        if saved.get("app_id") != app_id or saved.get("app_type") != runtime.definition.app_type:
            raise ValueError("存档与当前应用不匹配")
        state = saved.get("state")
        if not isinstance(state, dict):
            raise ValueError("存档状态格式无效")
        runtime.validate_state(state)
        runtime.state.replace(deepcopy(state))

    def load(self, app_id: str, session_id: str, slot: str = "auto") -> Dict[str, Any]:
        self._validate_slot(slot)
        saved = self._read(app_id, session_id, slot)
        if not saved:
            raise FileNotFoundError(f"save not found: {slot}")
        self._restore(app_id, session_id, saved)
        return saved

    def list_slots(self, app_id: str, session_id: str) -> list[Dict[str, Any]]:
        prefix = self._key(app_id, "")
        return [slot for slot in self.store.list_slots(session_id)
                if slot["slot_name"].startswith(prefix)
                and not slot["slot_name"].endswith(f":{self.CURRENT_SLOT}")]

    def delete(self, app_id: str, session_id: str, slot: str) -> bool:
        self._validate_slot(slot)
        return self.store.delete_slot(session_id, self._key(app_id, slot))

    @staticmethod
    def _validate_slot(slot: str) -> None:
        if not isinstance(slot, str) or not slot or len(slot) > 32:
            raise ValueError("存档槽位无效")

    def current_metadata(self, app_id: str, session_id: str) -> Dict[str, Any]:
        saved = self._read(app_id, session_id, self.CURRENT_SLOT)
        if not saved:
            return {"revision": 0, "updated_at": None}
        return {"revision": int(saved.get("revision", 0)),
                "updated_at": saved.get("updated_at")}
