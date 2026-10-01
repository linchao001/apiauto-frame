"""Session / case variable context."""

from __future__ import annotations

import threading
import uuid
from typing import Any, Iterator, Mapping, MutableMapping


class Context:
    """Thread-safe key-value store for cross-step correlation."""

    def __init__(
        self,
        *,
        product: str = "",
        env: str = "",
        initial: Mapping[str, Any] | None = None,
    ) -> None:
        self.product = product
        self.env = env
        self.trace_id = uuid.uuid4().hex
        self._data: MutableMapping[str, Any] = dict(initial or {})
        self._lock = threading.RLock()

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def update(self, values: Mapping[str, Any]) -> None:
        with self._lock:
            self._data.update(values)

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._data

    def __getitem__(self, key: str) -> Any:
        with self._lock:
            return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            return iter(dict(self._data))
