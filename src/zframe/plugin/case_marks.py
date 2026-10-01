"""Case metadata markers: ``case_title`` and priority ``P0`` / ``P1`` / ``P2``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from zframe.report.logging import get_logger

logger = get_logger("zframe.plugin.case_marks")

CASE_TITLE_MARKER = "case_title"
PRIORITY_MARKERS = ("P0", "P1", "P2")
# Lower rank = higher priority.
_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}

MARKER_HELP = (
    (
        CASE_TITLE_MARKER,
        'case_title(case_id=..., title=...): case id and human-readable title for reports',
    ),
    ("P0", "P0: highest priority case"),
    ("P1", "P1: medium priority case"),
    ("P2", "P2: lower priority case"),
)


@dataclass(frozen=True)
class CaseMeta:
    """Resolved case metadata for one pytest item (parametrize row + marks)."""

    case_id: str = ""
    title: str = ""
    priority: str | None = None

    @property
    def any(self) -> bool:
        return bool(self.case_id or self.title or self.priority)


def register_case_markers(config: pytest.Config) -> None:
    for name, help_text in MARKER_HELP:
        config.addinivalue_line("markers", f"{name}: {help_text}")


def parse_case_title(marker: Any) -> tuple[str, str]:
    """Extract ``(case_id, title)`` from a ``case_title`` marker."""
    kwargs = getattr(marker, "kwargs", {}) or {}
    args = getattr(marker, "args", ()) or ()

    case_id = str(kwargs.get("case_id") or "").strip()
    title = str(kwargs.get("title") or "").strip()

    if not case_id and len(args) >= 1:
        case_id = str(args[0]).strip()
    if not title and len(args) >= 2:
        title = str(args[1]).strip()
    return case_id, title


def resolve_priority(item: pytest.Item, *, warn: bool = True) -> str | None:
    """Return the highest priority among ``P0``/``P1``/``P2`` on ``item``.

    If more than one priority mark is present, warn and keep the highest (P0 > P1 > P2).
    """
    found = [name for name in PRIORITY_MARKERS if item.get_closest_marker(name) is not None]
    if not found:
        return None
    if len(found) > 1 and warn:
        chosen = min(found, key=lambda n: _PRIORITY_RANK[n])
        logger.warning(
            "multiple priority marks on %s: %s; using %s",
            getattr(item, "nodeid", item),
            ",".join(found),
            chosen,
        )
        return chosen
    return min(found, key=lambda n: _PRIORITY_RANK[n])


def parametrize_meta_data(item: pytest.Item) -> dict[str, Any]:
    """Read row-level ``meta_data`` from pytest parametrize ``callspec``."""
    callspec = getattr(item, "callspec", None)
    if callspec is None:
        return {}
    params = getattr(callspec, "params", {}) or {}
    meta = params.get("meta_data")
    return dict(meta) if isinstance(meta, dict) else {}


def _case_meta_from_row(row: dict[str, Any]) -> CaseMeta:
    case_id = str(row.get("id") or row.get("case_id") or "").strip()
    title = str(row.get("title") or "").strip()
    priority_raw = str(row.get("priority") or "").strip().upper()
    priority = priority_raw if priority_raw in PRIORITY_MARKERS else None
    return CaseMeta(case_id=case_id, title=title, priority=priority)


def _merge_priority(
    row_priority: str | None,
    mark_priority: str | None,
    *,
    item: pytest.Item,
    warn: bool,
) -> str | None:
    if row_priority and mark_priority and row_priority != mark_priority:
        chosen = min((row_priority, mark_priority), key=lambda p: _PRIORITY_RANK[p])
        if warn:
            logger.warning(
                "priority mismatch on %s: meta_data=%s vs marks=%s; using %s",
                getattr(item, "nodeid", item),
                row_priority,
                mark_priority,
                chosen,
            )
        return chosen
    return row_priority or mark_priority


def resolve_case_meta(item: pytest.Item, *, warn: bool = True) -> CaseMeta:
    """Resolve case metadata from parametrize ``meta_data`` and pytest marks.

    Row-level ``meta_data`` (``callspec.params``) overrides method-level
    ``@pytest.mark.case_title`` / ``P0``|``P1``|``P2`` for id and title.
    When both sources set priority and they differ, warn and keep the highest
    (P0 > P1 > P2), consistent with multiple priority marks on one item.
    """
    mark_case_id = ""
    mark_title = ""
    marker = item.get_closest_marker(CASE_TITLE_MARKER)
    if marker is not None:
        mark_case_id, mark_title = parse_case_title(marker)
    mark_priority = resolve_priority(item, warn=warn)

    row = parametrize_meta_data(item)
    if not row:
        return CaseMeta(case_id=mark_case_id, title=mark_title, priority=mark_priority)

    row_meta = _case_meta_from_row(row)
    case_id = row_meta.case_id or mark_case_id
    title = row_meta.title or mark_title
    priority = _merge_priority(row_meta.priority, mark_priority, item=item, warn=warn)

    if warn and row_meta.title and mark_title and row_meta.title != mark_title:
        logger.warning(
            "case title mismatch on %s: meta_data.title=%r vs case_title=%r; using meta_data",
            getattr(item, "nodeid", item),
            row_meta.title,
            mark_title,
        )

    return CaseMeta(case_id=case_id, title=title, priority=priority)


def format_case_summary(meta: CaseMeta) -> str:
    """One-line summary for HTML extras, e.g. ``E2E-01 [P0] 用户管理…``."""
    parts: list[str] = []
    if meta.case_id:
        parts.append(meta.case_id)
    if meta.priority:
        parts.append(f"[{meta.priority}]")
    if meta.title:
        parts.append(meta.title)
    return " ".join(parts)


def user_properties_for_meta(meta: CaseMeta) -> list[tuple[str, str]]:
    """Build pytest ``user_properties`` pairs from ``CaseMeta``."""
    props: list[tuple[str, str]] = []
    if meta.case_id:
        props.append(("case_id", meta.case_id))
    if meta.title:
        props.append(("title", meta.title))
    if meta.priority:
        props.append(("priority", meta.priority))
    return props


def warn_duplicate_priorities(items: list[pytest.Item]) -> None:
    """Emit warnings at collection for items with more than one priority mark."""
    for item in items:
        resolve_priority(item, warn=True)
