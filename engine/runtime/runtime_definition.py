"""通用应用定义：把配置、内容和启用能力统一交给运行时。"""
from copy import deepcopy
from typing import Any, Dict, Mapping


class RuntimeDefinition:
    """描述一个可运行应用，不绑定游戏、办公或故事领域。"""

    DEFAULT_CONFIG: Dict[str, Any] = {
        "app_id": "untitled",
        "app_type": "generic",
        "title": "Untitled Application",
        "description": "",
        "initial_page": None,
        "state": {},
        "features": [],
    }

    def __init__(self, config: Mapping[str, Any] | None = None,
                 data: Mapping[str, Any] | None = None):
        if config is not None and not isinstance(config, Mapping):
            raise TypeError("runtime config must be a mapping")
        if data is not None and not isinstance(data, Mapping):
            raise TypeError("runtime data must be a mapping")
        raw_config = dict(config or {})
        merged = {**self.DEFAULT_CONFIG, **raw_config}
        merged["state"] = deepcopy(raw_config.get("state", self.DEFAULT_CONFIG["state"]))
        merged["features"] = list(raw_config.get("features", self.DEFAULT_CONFIG["features"]))
        self.config: Dict[str, Any] = deepcopy(merged)
        self.data: Dict[str, Any] = deepcopy(dict(data or {}))

    @property
    def app_id(self) -> str:
        return self.config["app_id"]

    @property
    def app_type(self) -> str:
        return self.config["app_type"]

    @property
    def title(self) -> str:
        return self.config["title"]

    @property
    def initial_state(self) -> Dict[str, Any]:
        return deepcopy(self.config.get("state") or {})

    @property
    def initial_page(self) -> Any:
        return self.config.get("initial_page")

    def has_feature(self, feature: str) -> bool:
        return feature in self.config.get("features", [])

    def export(self) -> Dict[str, Any]:
        """导出定义的独立副本，适合传给 API 或保存器。"""
        return {
            "config": deepcopy(self.config),
            "data": deepcopy(self.data),
        }
