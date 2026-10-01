"""Select failed/error tests from a pytest-html report for re-run."""

from __future__ import annotations

import html as html_lib
import json
import re
from pathlib import Path
from typing import Any, Iterable

import pytest

HTML_FILENAME = "report.html"
FAILED_RESULTS = frozenset({"failed", "error"})
_PHASE_SUFFIX_RE = re.compile(r"::(setup|call|teardown)$", re.IGNORECASE)
_DATA_BLOB_RE = re.compile(
    r'id="data-container"[^>]*data-jsonblob="([^"]+)"',
    re.IGNORECASE | re.DOTALL,
)


class FromReportError(ValueError):
    """Invalid report path / payload, or no usable failed nodeids."""


def normalize_nodeid(nodeid: str) -> str:
    """Normalize path separators and strip pytest-html phase suffixes."""
    text = str(nodeid or "").strip().replace("\\", "/")
    return _PHASE_SUFFIX_RE.sub("", text)


def resolve_report_html_path(path: Path | str) -> Path:
    """Resolve a report.html file or a run directory containing it."""
    target = Path(path)
    if target.is_dir():
        target = target / HTML_FILENAME
    if not target.is_file():
        raise FromReportError(f"--from-report path not found: {path}")
    return target.resolve()


def _extract_blob(html_text: str) -> dict[str, Any]:
    match = _DATA_BLOB_RE.search(html_text)
    if not match:
        raise FromReportError(
            "--from-report: data-jsonblob not found (not a pytest-html report?)"
        )
    try:
        data = json.loads(html_lib.unescape(match.group(1)))
    except json.JSONDecodeError as exc:
        raise FromReportError(f"--from-report: invalid data-jsonblob JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise FromReportError("--from-report: data-jsonblob root must be an object")
    return data


def extract_failed_nodeids(report_path: Path | str) -> set[str]:
    """Return normalized nodeids with result Failed or Error from the HTML report."""
    html_path = resolve_report_html_path(report_path)
    text = html_path.read_text(encoding="utf-8", errors="replace")
    data = _extract_blob(text)
    tests = data.get("tests") or {}
    if not isinstance(tests, dict):
        raise FromReportError("--from-report: tests blob must be an object")

    failed: set[str] = set()
    for key, entry in tests.items():
        rows = entry if isinstance(entry, list) else [entry]
        for row in rows:
            if not isinstance(row, dict):
                continue
            result = str(row.get("result") or "").strip().lower()
            if result not in FAILED_RESULTS:
                continue
            raw_id = row.get("testId") or key
            nodeid = normalize_nodeid(str(raw_id))
            if nodeid:
                failed.add(nodeid)

    if not failed:
        raise FromReportError(
            f"--from-report: no failed/error cases in report: {html_path}"
        )
    return failed


def deselect_not_in_report(
    items: list[pytest.Item],
    wanted: Iterable[str],
) -> tuple[list[pytest.Item], list[pytest.Item]]:
    """Keep collected items whose nodeid is in ``wanted``; deselect the rest.

    Raises ``FromReportError`` when none of the wanted nodeids are present.
    """
    wanted_set = {normalize_nodeid(n) for n in wanted}
    kept: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    matched: set[str] = set()
    for item in items:
        nid = normalize_nodeid(item.nodeid)
        if nid in wanted_set:
            kept.append(item)
            matched.add(nid)
        else:
            deselected.append(item)
    if not kept:
        sample = ", ".join(sorted(wanted_set)[:5])
        more = "" if len(wanted_set) <= 5 else f" (+{len(wanted_set) - 5} more)"
        raise FromReportError(
            "--from-report: none of the failed/error nodeids matched the "
            f"current collection (sample: {sample}{more})"
        )
    return kept, deselected


def unmatched_wanted(wanted: Iterable[str], kept: list[pytest.Item]) -> list[str]:
    """Wanted nodeids that did not appear in the kept collection."""
    matched = {normalize_nodeid(i.nodeid) for i in kept}
    return sorted(normalize_nodeid(n) for n in wanted if normalize_nodeid(n) not in matched)
