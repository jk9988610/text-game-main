"""通用运行时状态：支持点号路径读写，并保持输入数据隔离。"""
from copy import deepcopy
from typing import Any, Dict


class RuntimeState:
    """保存一个应用会话的可变状态。

    路径使用点号分隔，例如 ``variables.chapter``。中间对象不存在时，
    ``set`` 和 ``update`` 会按需创建字典；``export`` 返回深拷贝，避免
    调用方绕过状态接口修改内部数据。
    """

    def __init__(self, initial: Dict[str, Any] | None = None):
        if initial is not None and not isinstance(initial, dict):
            raise TypeError("initial state must be a dictionary")
        self._data: Dict[str, Any] = deepcopy(initial or {})

    @staticmethod
    def _parts(path: str) -> list[str]:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("state path must be a non-empty string")
        parts = path.split(".")
        if any(not part for part in parts):
            raise ValueError(f"invalid state path: {path!r}")
        return parts

    def get(self, path: str, default: Any = None) -> Any:
        """读取路径；路径不存在时返回 ``default``。"""
        value: Any = self._data
        for part in self._parts(path):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]
        return value

    def set(self, path: str, value: Any) -> Any:
        """写入路径并返回写入值。"""
        parts = self._parts(path)
        target = self._data
        for part in parts[:-1]:
            current = target.get(part)
            if not isinstance(current, dict):
                current = {}
                target[part] = current
            target = current
        target[parts[-1]] = deepcopy(value)
        return value

    def update(self, path: str, amount: Any) -> Any:
        """对数值状态做增量更新，并返回更新后的值。"""
        current = self.get(path, 0)
        if not isinstance(current, (int, float)) or isinstance(current, bool):
            raise TypeError(f"state value at {path!r} is not numeric")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise TypeError("state update amount must be numeric")
        value = current + amount
        self.set(path, value)
        return value

    def has(self, path: str) -> bool:
        """判断路径是否存在，即使其值为 ``None`` 也返回 True。"""
        marker = object()
        return self.get(path, marker) is not marker

    def export(self) -> Dict[str, Any]:
        """导出状态的深拷贝。"""
        return deepcopy(self._data)

    def replace(self, data: Dict[str, Any]) -> None:
        """整体替换状态，用于读档或重置。"""
        if not isinstance(data, dict):
            raise TypeError("replacement state must be a dictionary")
        self._data = deepcopy(data)
