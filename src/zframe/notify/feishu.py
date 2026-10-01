"""Feishu (Lark) custom-bot webhook notifier."""

from __future__ import annotations

from typing import Any

import httpx

from zframe.notify.summary import RunSummary
from zframe.report.logging import get_logger

logger = get_logger("zframe.notify.feishu")


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {sec:.0f}s"
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours}h {minutes}m"


def build_feishu_card(summary: RunSummary) -> dict[str, Any]:
    """Build an interactive card payload (no per-case failure list)."""
    template = "green" if summary.ok else "red"
    title = summary.title or "ZFrame 测试结果"

    fields = [
        {
            "is_short": True,
            "text": {"tag": "lark_md", "content": f"**产品**\n{summary.product or '-'}"},
        },
        {
            "is_short": True,
            "text": {"tag": "lark_md", "content": f"**环境**\n{summary.env or '-'}"},
        },
        {
            "is_short": True,
            "text": {"tag": "lark_md", "content": f"**结果**\n{summary.result_label}"},
        },
        {
            "is_short": True,
            "text": {
                "tag": "lark_md",
                "content": f"**耗时**\n{_format_duration(summary.duration_s)}",
            },
        },
        {
            "is_short": True,
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**统计**\n"
                    f"通过 {summary.passed} / 失败 {summary.failed} / "
                    f"跳过 {summary.skipped} / 错误 {summary.error} "
                    f"（共 {summary.total}）"
                ),
            },
        },
    ]
    if summary.report_path:
        fields.append(
            {
                "is_short": False,
                "text": {
                    "tag": "lark_md",
                    "content": f"**报告**\n{summary.report_path}",
                },
            }
        )

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": template,
            },
            "elements": [
                {"tag": "div", "fields": fields[:5]},
                *([{"tag": "div", "fields": fields[5:]}] if len(fields) > 5 else []),
            ],
        },
    }


class FeishuNotifier:
    """POST an interactive card to a Feishu custom-bot webhook."""

    def __init__(self, webhook: str, *, timeout: float = 10.0) -> None:
        self.webhook = webhook.strip()
        self.timeout = timeout

    def send(self, summary: RunSummary) -> None:
        if not self.webhook:
            raise ValueError("Feishu webhook URL is empty")
        payload = build_feishu_card(summary)
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self.webhook, json=payload)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        # Feishu returns {"code": 0, "msg": "success"} on success.
        code = body.get("code") if isinstance(body, dict) else None
        if resp.status_code >= 400 or (code is not None and code != 0):
            raise RuntimeError(
                f"Feishu notify failed: status={resp.status_code} body={body}"
            )
        logger.info("feishu notify ok (status=%s)", summary.result_label)
