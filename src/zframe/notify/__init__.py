"""Session-end test result notifications (Feishu, …)."""

from zframe.notify.factory import (
    build_notifier,
    register_notifier,
    registered_notifier_types,
)
from zframe.notify.feishu import FeishuNotifier, build_feishu_card
from zframe.notify.summary import (
    RunSummary,
    collect_run_summary,
    render_title,
    should_notify,
)

__all__ = [
    "FeishuNotifier",
    "RunSummary",
    "build_feishu_card",
    "build_notifier",
    "collect_run_summary",
    "register_notifier",
    "registered_notifier_types",
    "render_title",
    "should_notify",
]
