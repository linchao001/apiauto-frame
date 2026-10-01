"""Device / env targeting helpers for multi-device API runs."""

from __future__ import annotations

from typing import Iterable

import pytest


DEVICE_MARKER = "device"


def marker_devices(item: pytest.Item) -> frozenset[str] | None:
    """Return allowed env names from ``@pytest.mark.device(...)``, or ``None`` if unmarked."""
    marker = item.get_closest_marker(DEVICE_MARKER)
    if marker is None:
        return None
    names = [str(a).strip() for a in marker.args if str(a).strip()]
    names.extend(str(v).strip() for v in marker.kwargs.values() if str(v).strip())
    return frozenset(names)


def should_run_on_env(item: pytest.Item, env: str) -> bool:
    """Unmarked tests run on every env; marked tests only on listed envs."""
    allowed = marker_devices(item)
    if allowed is None:
        return True
    return env in allowed


def deselect_for_env(
    items: list[pytest.Item],
    env: str,
) -> tuple[list[pytest.Item], list[pytest.Item]]:
    """Split collected items into (kept, deselected) for the active ``env``."""
    kept: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        if should_run_on_env(item, env):
            kept.append(item)
        else:
            deselected.append(item)
    return kept, deselected


def format_device_skip_reason(env: str, allowed: Iterable[str]) -> str:
    names = ", ".join(sorted(allowed))
    return f"device filter: env={env!r} not in {{{names}}}"
