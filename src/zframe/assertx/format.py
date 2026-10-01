"""Human-readable assertion failure formatting (diff-first, minimal noise)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from zframe.client.response import Response

_DIFF_EXPECT_GOT = re.compile(
    r"^(?P<path>[^:]+): expected (?P<expected>.+), got (?P<actual>.+)$"
)
_DIFF_STATUS = re.compile(
    r"^status: expected (?P<expected>.+), got (?P<actual>.+)$"
)


@dataclass(frozen=True)
class _DiffRow:
    field: str
    expected: str
    actual: str


def _parse_diff_line(line: str) -> _DiffRow | None:
    text = line.strip()
    match = _DIFF_STATUS.match(text)
    if match:
        return _DiffRow("status", match.group("expected"), match.group("actual"))
    match = _DIFF_EXPECT_GOT.match(text)
    if match:
        return _DiffRow(match.group("path"), match.group("expected"), match.group("actual"))
    return None


def _format_table(rows: list[_DiffRow]) -> str:
    field_w = max(len("Field"), *(len(r.field) for r in rows))
    exp_w = max(len("Expected"), *(len(r.expected) for r in rows))
    act_w = max(len("Actual"), *(len(r.actual) for r in rows))
    header = f"  {'Field'.ljust(field_w)}  {'Expected'.ljust(exp_w)}  Actual"
    sep = f"  {'-' * field_w}  {'-' * exp_w}  {'-' * act_w}"
    body = [
        f"  {r.field.ljust(field_w)}  {r.expected.ljust(exp_w)}  {r.actual}"
        for r in rows
    ]
    return "\n".join([header, sep, *body])


def _response_body_hint(response: Response, *, max_fields: int = 6) -> list[str]:
    """Short body preview when status (or other top-level) assertion fails."""
    try:
        body = response.json()
    except Exception:
        text = (response.text or "").strip()
        if not text:
            return []
        preview = text if len(text) <= 200 else text[:200] + "…"
        return [f"  {preview}"]

    if not isinstance(body, dict):
        return [f"  {body!r}"]

    lines: list[str] = []
    for index, (key, value) in enumerate(body.items()):
        if index >= max_fields:
            lines.append("  …")
            break
        lines.append(f"  {key}: {_preview_value(value)}")
    return lines


def _preview_value(value: Any, *, max_len: int = 80) -> str:
    text = repr(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def format_assertion_failure(
    label: str,
    diffs: list[str],
    *,
    response: Response | None = None,
    show_body_hint: bool = False,
) -> str:
    """Build a compact, diff-first failure message for terminal / reports."""
    lines: list[str] = []
    if len(diffs) > 1:
        lines.append(f"Assertion failed: {label} ({len(diffs)} differences)")
    else:
        lines.append(f"Assertion failed: {label}")

    bar_len = min(72, max(40, len(lines[0]) + 8))
    lines.append("─" * bar_len)

    if diffs:
        parsed = [_parse_diff_line(item) for item in diffs]
        if parsed and all(row is not None for row in parsed):
            lines.append(_format_table([row for row in parsed if row is not None]))
        else:
            for item in diffs:
                lines.append(f"  • {item}")

    if show_body_hint and response is not None:
        hint = _response_body_hint(response)
        if hint:
            lines.append("")
            lines.append("Response body (context):")
            lines.extend(hint)

    return "\n".join(lines)


def format_plain_failure(message: str) -> str:
    """Wrap a single-line failure without structured diffs."""
    lines = ["Assertion failed", "─" * 40, f"  • {message}"]
    return "\n".join(lines)
