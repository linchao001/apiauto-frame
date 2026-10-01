"""Optional pytest-html extras (no hard dependency at import time)."""

from __future__ import annotations

import html
import json
from contextlib import contextmanager
from typing import Any, Iterator

from zframe.client.response import Response
from zframe.report.capture import get_test_item


def _queue_extra(extra: dict[str, Any]) -> None:
    item = get_test_item()
    if item is None:
        return
    extras = getattr(item, "_zframe_html_extras", None)
    if extras is None:
        extras = []
        item._zframe_html_extras = extras  # type: ignore[attr-defined]
    extras.append(extra)


def _make_extra(*, kind: str, content: str, name: str = "") -> dict[str, Any] | None:
    try:
        from pytest_html import extras
    except ImportError:
        return None
    if kind == "html":
        return extras.html(content)
    if kind == "json":
        return extras.json(content, name=name or "json")
    return extras.text(content, name=name or "Text")


def pop_html_extras(item: Any) -> list[dict[str, Any]]:
    """Take queued extras from the pytest item (clears the queue)."""
    extras = getattr(item, "_zframe_html_extras", None) or []
    item._zframe_html_extras = []  # type: ignore[attr-defined]
    return list(extras)


def pop_steps(item: Any) -> list[tuple[str, str]]:
    """Take recorded ``(title, status)`` steps from the item (clears the queue)."""
    steps = getattr(item, "_zframe_steps", None) or []
    item._zframe_steps = []  # type: ignore[attr-defined]
    return list(steps)


def _record_step(title: str, status: str) -> None:
    item = get_test_item()
    if item is None:
        return
    steps = getattr(item, "_zframe_steps", None)
    if steps is None:
        steps = []
        item._zframe_steps = steps  # type: ignore[attr-defined]
    steps.append((title, status))


@contextmanager
def step(title: str) -> Iterator[None]:
    """Record a named step for the HTML report (rendered as visible HTML, not links)."""
    try:
        yield
    except BaseException:
        _record_step(title, "fail")
        raise
    else:
        _record_step(title, "ok")


def _queue_extra_safe(kind: str, content: str, *, name: str = "") -> None:
    extra = _make_extra(kind=kind, content=content, name=name)
    if extra is not None:
        _queue_extra(extra)


def attach_response(response: Response, name: str = "response") -> None:
    payload = response.to_dict()
    body = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    _queue_extra_safe("json", body, name=name)


def attach_text(body: str, name: str = "attachment") -> None:
    _queue_extra_safe("text", body, name=name)


def extras_for_response(response: Response, name: str = "response") -> list[dict[str, Any]]:
    """Build pytest-html extras for a response without requiring an active item."""
    payload = response.to_dict()
    body = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    extra = _make_extra(kind="json", content=body, name=name)
    return [extra] if extra is not None else []


def extras_for_text(body: str, name: str = "attachment") -> list[dict[str, Any]]:
    """Build a text extra without requiring an active item."""
    extra = _make_extra(kind="text", content=body, name=name)
    return [extra] if extra is not None else []


def extras_for_html(content: str) -> list[dict[str, Any]]:
    """Build an inline HTML extra (visible in the expanded test details)."""
    extra = _make_extra(kind="html", content=content)
    return [extra] if extra is not None else []


_STEP_ICON = {"ok": "✔", "fail": "✖"}


def render_case_detail_html(
    *,
    case_id: str = "",
    title: str = "",
    priority: str | None = None,
    steps: list[tuple[str, str]] | None = None,
) -> str:
    """Build escaped HTML for case meta + steps shown in the report details pane."""
    parts: list[str] = ['<div class="zframe-case-detail">']
    head: list[str] = []
    if case_id:
        head.append(f"<strong>{html.escape(case_id)}</strong>")
    if priority:
        head.append(f"<span>[{html.escape(priority)}]</span>")
    if title:
        head.append(html.escape(title))
    if head:
        parts.append(f'<div class="zframe-case-title">{" ".join(head)}</div>')
    if steps:
        parts.append('<ol class="zframe-steps">')
        for step_title, status in steps:
            icon = _STEP_ICON.get(status, "•")
            parts.append(
                f"<li>{html.escape(icon)} {html.escape(step_title)}</li>"
            )
        parts.append("</ol>")
    parts.append("</div>")
    return "".join(parts)


def render_title_cell_html(*, title: str, detail_html: str = "") -> str:
    """Title column cell with optional hover popup for case details."""
    label = html.escape(title) if title.strip() else ""
    detail = (detail_html or "").strip()
    if not detail:
        return f'<td class="col-caseTitle">{label}</td>'
    trigger = label or "详情"
    return (
        '<td class="col-caseTitle">'
        f'<span class="zframe-title-trigger" tabindex="0">{trigger}</span>'
        f'<div class="zframe-title-popup" role="tooltip">{detail}</div>'
        "</td>"
    )
