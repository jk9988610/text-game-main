"""应用运行时适配器的统一协议。"""
from typing import Any, Mapping, Protocol

from .runtime_definition import RuntimeDefinition
from .runtime_state import RuntimeState


class ApplicationRuntime(Protocol):
    """所有可注册应用运行时必须提供的最小接口。"""

    definition: RuntimeDefinition
    state: RuntimeState

    def payload(self) -> dict[str, Any]:
        """返回供 API 和前端使用的当前状态。"""
        ...

    def transition(self, index: int) -> Any:
        """执行一个可见转移。"""
        ...

    def validate_state(self, state: Mapping[str, Any]) -> None:
        """验证外部存档状态是否仍适用于当前模板。"""
        ...
