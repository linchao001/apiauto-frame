"""Tests for session-end notify (Feishu)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from zframe.config.loader import load_settings
from zframe.config.models import NotifySettings
from zframe.notify.factory import build_notifier, registered_notifier_types
from zframe.notify.feishu import FeishuNotifier, build_feishu_card
from zframe.notify.summary import (
    RunSummary,
    collect_run_summary,
    render_title,
    should_notify,
)


def test_notify_settings_configured():
    assert NotifySettings().configured is False
    # webhook alone does not enable (local/dev default off)
    assert NotifySettings(webhook="https://example/hook").configured is False
    assert NotifySettings(enabled=False, webhook="https://example/hook").configured is False
    assert NotifySettings(enabled=True, webhook="https://example/hook").configured is True


def test_load_settings_notify(tmp_path: Path):
    config = tmp_path / "config"
    (config / "env").mkdir(parents=True)
    (config / "product.yaml").write_text(
        "product: sample\n"
        "notify:\n"
        "  enabled: true\n"
        "  type: feishu\n"
        "  webhook: https://open.feishu.cn/open-apis/bot/v2/hook/sample\n"
        '  title: "ZFrame · ${product}/${env}"\n',
        encoding="utf-8",
    )
    (config / "env" / "test.yaml").write_text("vars: {}\n", encoding="utf-8")
    settings = load_settings(env="test", config_dir=config)
    assert settings.notify.configured
    assert settings.notify.type == "feishu"
    assert settings.notify.on == "always"
    assert "hook/sample" in settings.notify.webhook
    assert settings.notify.title == "ZFrame · ${product}/${env}"
    assert "notify" not in settings.extra


def test_load_settings_notify_default_disabled(tmp_path: Path):
    """Webhook in YAML without enabled → still off (local/dev safe)."""
    config = tmp_path / "config"
    (config / "env").mkdir(parents=True)
    (config / "product.yaml").write_text(
        "product: sample\n"
        "notify:\n"
        "  type: feishu\n"
        "  webhook: https://open.feishu.cn/open-apis/bot/v2/hook/sample\n",
        encoding="utf-8",
    )
    (config / "env" / "test.yaml").write_text("vars: {}\n", encoding="utf-8")
    settings = load_settings(env="test", config_dir=config)
    assert settings.notify.enabled is False
    assert settings.notify.configured is False
    assert "hook/sample" in settings.notify.webhook


def test_should_notify_policies():
    assert should_notify(on="always", exitstatus=0) is True
    assert should_notify(on="always", exitstatus=1) is True
    assert should_notify(on="failure", exitstatus=0) is False
    assert should_notify(on="failure", exitstatus=1) is True
    assert should_notify(on="success", exitstatus=0) is True
    assert should_notify(on="success", exitstatus=1) is False


def test_render_title():
    assert render_title("", product="acme", env="test") == "ZFrame 测试结果 · acme/test"
    assert render_title("ZFrame · ${product}/${env}", product="acme", env="uat") == "ZFrame · acme/uat"
    assert render_title("{product}-{env}", product="a", env="b") == "a-b"


def test_build_feishu_card_summary_only():
    summary = RunSummary(
        product="acme",
        env="test",
        passed=3,
        failed=1,
        skipped=0,
        error=0,
        total=4,
        duration_s=12.5,
        exitstatus=1,
        report_path="reports/20260101/report.html",
        title="ZFrame · acme/test",
    )
    payload = build_feishu_card(summary)
    assert payload["msg_type"] == "interactive"
    assert payload["card"]["header"]["template"] == "red"
    assert payload["card"]["header"]["title"]["content"] == "ZFrame · acme/test"
    # No failure nodeid list — only summary fields.
    blob = str(payload)
    assert "通过 3" in blob
    assert "失败 1" in blob
    assert "reports/20260101/report.html" in blob
    assert "test_foo" not in blob


def test_build_notifier_feishu():
    assert "feishu" in registered_notifier_types()
    assert build_notifier(NotifySettings(webhook="https://example/hook")) is None
    n = build_notifier(NotifySettings(enabled=True, webhook="https://example/hook"))
    assert isinstance(n, FeishuNotifier)
    assert build_notifier(NotifySettings()) is None


@respx.mock
def test_feishu_notifier_sends_card():
    route = respx.post("https://open.feishu.cn/open-apis/bot/v2/hook/x").mock(
        return_value=httpx.Response(200, json={"code": 0, "msg": "success"})
    )
    notifier = FeishuNotifier("https://open.feishu.cn/open-apis/bot/v2/hook/x")
    summary = RunSummary(
        product="acme",
        env="test",
        passed=1,
        failed=0,
        skipped=0,
        error=0,
        total=1,
        duration_s=1.0,
        exitstatus=0,
        title="ok",
    )
    notifier.send(summary)
    assert route.called
    body = route.calls.last.request.read()
    assert b"interactive" in body


@respx.mock
def test_feishu_notifier_raises_on_api_error():
    respx.post("https://open.feishu.cn/open-apis/bot/v2/hook/x").mock(
        return_value=httpx.Response(200, json={"code": 19001, "msg": "bad"})
    )
    notifier = FeishuNotifier("https://open.feishu.cn/open-apis/bot/v2/hook/x")
    summary = RunSummary(
        product="acme",
        env="test",
        passed=0,
        failed=1,
        skipped=0,
        error=0,
        total=1,
        duration_s=0.1,
        exitstatus=1,
    )
    with pytest.raises(RuntimeError, match="Feishu notify failed"):
        notifier.send(summary)


def test_collect_run_summary_from_session():
    session = MagicMock()
    session.exitstatus = 0
    session.testscollected = 2
    reporter = MagicMock()
    reporter.stats = {
        "passed": [object(), object()],
        "failed": [],
        "skipped": [],
        "error": [],
    }
    session.config.pluginmanager.get_plugin.return_value = reporter
    session.config._zframe_session_start = None

    summary = collect_run_summary(
        session,
        product="acme",
        env="test",
        title="t",
        duration_s=3.2,
    )
    assert summary.passed == 2
    assert summary.total == 2
    assert summary.ok is True
    assert summary.duration_s == 3.2
