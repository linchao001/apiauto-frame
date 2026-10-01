"""Dynamic expected-value matchers for body assertions."""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from typing import Any


class Matcher(ABC):
    """Base for values that match dynamically instead of by equality."""

    @abstractmethod
    def matches(self, actual: Any) -> bool:
        raise NotImplementedError

    def describe(self) -> str:
        return repr(self)


class AnyMatcher(Matcher):
    """Match any actual value (field must still exist unless excluded)."""

    def matches(self, actual: Any) -> bool:
        return True

    def __repr__(self) -> str:
        return "ANY"


ANY = AnyMatcher()


class Regex(Matcher):
    """Match when ``actual`` is a string matching ``pattern`` (``re.search``)."""

    def __init__(self, pattern: str, *, flags: int = 0) -> None:
        self.pattern = pattern
        self.flags = flags
        self._compiled = re.compile(pattern, flags)

    def matches(self, actual: Any) -> bool:
        return isinstance(actual, str) and self._compiled.search(actual) is not None

    def __repr__(self) -> str:
        return f"Regex({self.pattern!r})"


class Approx(Matcher):
    """Numeric match with absolute / relative tolerance (pytest.approx-style)."""

    def __init__(
        self,
        value: float,
        *,
        abs: float | None = None,  # noqa: A002
        rel: float | None = None,
    ) -> None:
        self.value = float(value)
        self.abs = abs
        self.rel = rel

    def matches(self, actual: Any) -> bool:
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            return False
        actual_f = float(actual)
        if math.isnan(self.value) or math.isnan(actual_f):
            return math.isnan(self.value) and math.isnan(actual_f)
        tol_abs = 0.0 if self.abs is None else self.abs
        tol_rel = 1e-6 if self.rel is None and self.abs is None else (0.0 if self.rel is None else self.rel)
        tolerance = max(tol_abs, abs(self.value) * tol_rel)
        return abs(actual_f - self.value) <= tolerance

    def __repr__(self) -> str:
        parts = [repr(self.value)]
        if self.abs is not None:
            parts.append(f"abs={self.abs}")
        if self.rel is not None:
            parts.append(f"rel={self.rel}")
        return f"Approx({', '.join(parts)})"


def coerce_expected(value: Any) -> Any:
    """Resolve JSON matcher markers and leave Python matchers unchanged.

    Supported markers::

        {"$any": true}
        {"$regex": "^admin"}
        {"$approx": 1.23, "abs": 0.01, "rel": 1e-6}
    """
    if isinstance(value, Matcher):
        return value
    if isinstance(value, dict):
        if "$any" in value:
            return ANY
        if "$regex" in value:
            flags = value.get("flags", 0)
            return Regex(str(value["$regex"]), flags=int(flags) if flags is not None else 0)
        if "$approx" in value:
            return Approx(
                value["$approx"],
                abs=value.get("abs"),
                rel=value.get("rel"),
            )
        return {key: coerce_expected(item) for key, item in value.items()}
    if isinstance(value, list):
        return [coerce_expected(item) for item in value]
    return value
