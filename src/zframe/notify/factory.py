"""Build Notifier from settings via a type registry."""

from __future__ import annotations

from typing import Any, Callable

from zframe.config.models import NotifySettings, Settings
from zframe.notify.base import Notifier
from zframe.notify.feishu import FeishuNotifier

NotifierFactory = Callable[[NotifySettings], Notifier]

_REGISTRY: dict[str, NotifierFactory] = {}


def register_notifier(kind: str, factory: NotifierFactory) -> None:
    """Register or override a notifier factory for ``notify.type``."""
    key = kind.strip().lower()
    if not key:
        raise ValueError("notify type name must be non-empty")
    _REGISTRY[key] = factory


def registered_notifier_types() -> list[str]:
    return sorted(_REGISTRY)


def build_notifier(
    settings: Settings | NotifySettings | dict[str, Any] | None,
) -> Notifier | None:
    """Create a :class:`Notifier` from notify settings.

    Returns ``None`` when notify is not configured (empty webhook / disabled).
    Unknown ``notify.type`` raises ``ValueError``.
    """
    if settings is None:
        return None
    if isinstance(settings, Settings):
        cfg = settings.notify
    elif isinstance(settings, NotifySettings):
        cfg = settings
    else:
        cfg = NotifySettings.model_validate(dict(settings or {}))

    if not cfg.configured:
        return None

    kind = str(cfg.type or "feishu").strip().lower() or "feishu"
    factory = _REGISTRY.get(kind)
    if factory is None:
        known = ", ".join(registered_notifier_types()) or "(none)"
        raise ValueError(f"Unknown notify type {kind!r}. Registered: {known}")
    return factory(cfg)


def _feishu_factory(cfg: NotifySettings) -> Notifier:
    return FeishuNotifier(cfg.webhook)


def _register_builtins() -> None:
    register_notifier("feishu", _feishu_factory)
    register_notifier("lark", _feishu_factory)


_register_builtins()
