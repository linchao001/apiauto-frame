"""Simple ``${var}`` / ``${a.b}`` template rendering."""

from __future__ import annotations

import re
from typing import Any, Mapping

_PATTERN = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")


def _lookup(context: Mapping[str, Any], expr: str) -> Any:
    cur: Any = context
    for part in expr.split("."):
        if isinstance(cur, Mapping) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(expr)
    return cur


def render(value: Any, context: Mapping[str, Any]) -> Any:
    """Recursively render ``${...}`` placeholders in strings / containers."""
    if isinstance(value, str):
        matches = list(_PATTERN.finditer(value))
        if not matches:
            return value
        if len(matches) == 1 and matches[0].span() == (0, len(value)):
            return _lookup(context, matches[0].group(1))
        def repl(match: re.Match[str]) -> str:
            return str(_lookup(context, match.group(1)))
        return _PATTERN.sub(repl, value)
    if isinstance(value, list):
        return [render(item, context) for item in value]
    if isinstance(value, dict):
        return {k: render(v, context) for k, v in value.items()}
    return value
