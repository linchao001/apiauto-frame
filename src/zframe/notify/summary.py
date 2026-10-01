"""Collect pytest session stats into a run summary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunSummary:
    """Aggregated result of one pytest session."""

    product: str
    env: str
    passed: int
    failed: int
    skipped: int
    error: int
    total: int
    duration_s: float
    exitstatus: int
    report_path: str = ""
    title: str = ""

    @property
    def ok(self) -> bool:
        return self.exitstatus == 0 and self.failed == 0 and self.error == 0

    @property
    def result_label(self) -> str:
        return "通过" if self.ok else "失败"


def _count(stats: dict[str, Any], key: str) -> int:
    items = stats.get(key) or []
    return len(items) if isinstance(items, list) else int(items or 0)


def collect_run_summary(
    session: Any,
    *,
    product: str = "",
    env: str = "",
    report_dir: Path | str | None = None,
    title: str = "",
    duration_s: float | None = None,
) -> RunSummary:
    """Build :class:`RunSummary` from a finished pytest session."""
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    stats: dict[str, Any] = getattr(reporter, "stats", {}) if reporter else {}

    passed = _count(stats, "passed")
    failed = _count(stats, "failed")
    skipped = _count(stats, "skipped")
    error = _count(stats, "error")
    # xfailed / xpassed are informational; include in total via collected if available
    total = passed + failed + skipped + error
    collected = getattr(session, "testscollected", None)
    if isinstance(collected, int) and collected > total:
        total = collected

    if duration_s is None:
        duration_s = 0.0
        start = getattr(session.config, "_zframe_session_start", None)
        if start is not None:
            import time

            duration_s = max(0.0, time.time() - float(start))
        elif reporter is not None:
            duration_s = float(getattr(reporter, "_session_duration", 0) or 0)

    report_path = ""
    if report_dir is not None:
        path = Path(report_dir)
        html = path / "report.html"
        report_path = str(html if html.is_file() else path)

    exitstatus = int(getattr(session, "exitstatus", 0) or 0)

    return RunSummary(
        product=product,
        env=env,
        passed=passed,
        failed=failed,
        skipped=skipped,
        error=error,
        total=total,
        duration_s=duration_s,
        exitstatus=exitstatus,
        report_path=report_path,
        title=title,
    )


def should_notify(*, on: str, exitstatus: int) -> bool:
    """Return whether notification should fire for the given policy."""
    policy = (on or "always").strip().lower()
    if policy == "always":
        return True
    if policy == "failure":
        return exitstatus != 0
    if policy == "success":
        return exitstatus == 0
    return True


def render_title(template: str, *, product: str, env: str) -> str:
    """Expand ``${product}`` / ``${env}`` (and ``{product}`` / ``{env}``) in a title."""
    text = (template or "").strip()
    if not text:
        parts = [p for p in (product, env) if p]
        return f"ZFrame 测试结果 · {'/'.join(parts)}" if parts else "ZFrame 测试结果"
    return (
        text.replace("${product}", product)
        .replace("${env}", env)
        .replace("{product}", product)
        .replace("{env}", env)
    )
