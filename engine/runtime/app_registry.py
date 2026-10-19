"""数据驱动应用注册中心。"""
import json
from pathlib import Path
from typing import Any, Dict

from .form_runtime import FormFlowRuntime
from .runtime_definition import RuntimeDefinition
from .story_runtime import InteractiveStoryRuntime
from .task_runtime import TaskFlowRuntime


class AppRegistry:
    """扫描 templates 下的应用清单，并按类型创建运行时。"""

    def __init__(self, templates_dir: str | Path):
        self.templates_dir = Path(templates_dir)
        self._apps: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        apps: Dict[str, Dict[str, Any]] = {}
        if self.templates_dir.exists():
            for directory in sorted(self.templates_dir.iterdir()):
                manifest_path = directory / "app.json"
                if not directory.is_dir() or not manifest_path.exists():
                    continue
                with manifest_path.open(encoding="utf-8") as handle:
                    config = json.load(handle)
                app_id = config.get("app_id")
                app_type = config.get("app_type")
                if not isinstance(app_id, str) or not app_id.strip():
                    raise ValueError(f"应用 {directory.name} 缺少 app_id")
                if app_id in apps:
                    raise ValueError(f"应用 ID 重复：{app_id}")
                if not isinstance(app_type, str) or not app_type.strip():
                    raise ValueError(f"应用 {app_id} 缺少 app_type")
                apps[app_id] = {
                    "app_id": app_id,
                    "app_type": app_type,
                    "title": config.get("title", app_id),
                    "description": config.get("description", ""),
                    "directory": directory,
                    "config": config,
                }
        self._apps = apps

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._apps))

    def get(self, app_id: str) -> Dict[str, Any] | None:
        app = self._apps.get(app_id)
        return dict(app) if app else None

    def catalog(self) -> list[Dict[str, Any]]:
        return [
            {key: value for key, value in app.items() if key != "directory" and key != "config"}
            for app in (self._apps[app_id] for app_id in self.ids())
        ]

    def create_runtime(self, app_id: str):
        app = self._apps.get(app_id)
        if not app:
            raise KeyError(f"unknown application: {app_id}")
        app_type = app["app_type"]
        directory = app["directory"]
        factories = {
            "interactive_story": InteractiveStoryRuntime,
            "task_flow": TaskFlowRuntime,
            "form_flow": FormFlowRuntime,
        }
        runtime_type = factories.get(app_type)
        if runtime_type is None:
            raise ValueError(f"unsupported application type: {app_type}")
        return runtime_type.from_directory(directory)

    def definition(self, app_id: str) -> RuntimeDefinition:
        app = self._apps.get(app_id)
        if not app:
            raise KeyError(f"unknown application: {app_id}")
        return RuntimeDefinition(app["config"])
