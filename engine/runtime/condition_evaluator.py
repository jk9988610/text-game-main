"""通用条件求值器。"""
from typing import Any, Mapping

from .runtime_state import RuntimeState


class ConditionEvaluator:
    """根据运行时状态判断声明式条件。"""

    OPERATORS = {
        "equals": lambda actual, expected: actual == expected,
        "not_equals": lambda actual, expected: actual != expected,
        "greater_than": lambda actual, expected: actual > expected,
        "greater_or_equal": lambda actual, expected: actual >= expected,
        "less_than": lambda actual, expected: actual < expected,
        "less_or_equal": lambda actual, expected: actual <= expected,
    }

    def __init__(self, state: RuntimeState):
        self.state = state

    def matches(self, condition: Mapping[str, Any] | None) -> bool:
        if not condition:
            return True
        if not isinstance(condition, Mapping):
            raise TypeError("condition must be a mapping")
        path = condition.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("condition path must be a non-empty string")
        actual = self.state.get(path)
        operator = condition.get("operator", "equals")
        if operator == "truthy":
            return bool(actual)
        if operator == "falsy":
            return not bool(actual)
        comparator = self.OPERATORS.get(operator)
        if comparator is None:
            raise ValueError(f"unknown condition operator: {operator}")
        try:
            return comparator(actual, condition.get("value"))
        except TypeError:
            return False
