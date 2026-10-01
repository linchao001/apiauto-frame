"""Resolve case-side call site and compact call-phase failure repr."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Any

import zframe

from zframe.assertx.checkers import AssertionErrorX

# (abspath, lineno, funcname)
FailureSite = tuple[str, int, str]

_ZFRAME_ROOT = Path(zframe.__file__).resolve().parent


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _is_internal_frame(filename: str) -> bool:
    """True for zframe package, pytest, and installed deps — not case code."""
    if not filename or filename.startswith("<"):
        return True
    path = Path(filename)
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    try:
        if resolved.is_relative_to(_ZFRAME_ROOT):
            return True
    except (ValueError, AttributeError):
        # Python < 3.9 or path quirks — fall through to string checks.
        root = _norm(str(_ZFRAME_ROOT))
        if _norm(str(resolved)).startswith(root + os.sep):
            return True
    norm = _norm(str(resolved))
    parts = set(Path(norm).parts)
    if "site-packages" in parts or "dist-packages" in parts:
        return True
    # pytest / pluggy runners sitting outside site-packages (editable / src).
    if "_pytest" in parts or "pluggy" in parts:
        return True
    return False


def resolve_case_failure_site(exc: BaseException) -> FailureSite | None:
    """Return the deepest non-framework frame for ``exc``.

    Walks from the raise site outward, skipping zframe / pytest / site-packages
    so callers get the case (or case-helper) line that invoked ``check(...)``.
    """
    tb: TracebackType | None = exc.__traceback__
    frames: list[TracebackType] = []
    while tb is not None:
        frames.append(tb)
        tb = tb.tb_next
    for frame_tb in reversed(frames):
        code = frame_tb.tb_frame.f_code
        filename = code.co_filename
        if _is_internal_frame(filename):
            continue
        return (filename, frame_tb.tb_lineno, code.co_name)
    return None


def format_site_line(site: FailureSite) -> str:
    """Compact ``at file.py:line in func`` for reports / logs."""
    path, lineno, func = site
    name = Path(path).name
    return f"at {name}:{lineno} in {func}"


def format_failure_at(message: str, site: FailureSite | None) -> str:
    """Prepend case-site line to a compact assertion message (no full traceback)."""
    if site is None:
        return message
    return f"{format_site_line(site)}\n{message}"


def format_call_failure(exc: BaseException, site: FailureSite | None) -> str:
    """Compact call-phase failure: site + message, no source dump.

    ``AssertionErrorX`` keeps its diff-first message; other exceptions become
    ``ExcType: detail`` (or just the type name when the message is empty).
    """
    if isinstance(exc, AssertionErrorX):
        return format_failure_at(str(exc), site)
    detail = str(exc).strip()
    typename = type(exc).__name__
    body = f"{typename}: {detail}" if detail else typename
    return format_failure_at(body, site)


def should_compact_call_failures(invocation_args: Sequence[str]) -> bool:
    """True unless the user explicitly passed ``--tb`` / ``--tb=...``.

    Escape hatch: ``--tb=short|long|auto|native|line|no`` restores pytest's
    traceback style (framework leaves ``longrepr`` alone).
    """
    for arg in invocation_args:
        if arg == "--tb" or arg.startswith("--tb="):
            return False
    return True


def apply_case_failure_location(report: Any, exc: BaseException) -> FailureSite | None:
    """Set ``report.location`` lineno to the case call site when resolvable.

    Keeps path / domain from the existing location tuple; only replaces lineno.
    pytest stores location lineno as **0-based**; traceback ``tb_lineno`` is 1-based.
    """
    site = resolve_case_failure_site(exc)
    if site is None:
        return None
    path, lineno, _func = site
    zero_based = max(lineno - 1, 0)
    loc = getattr(report, "location", None)
    if isinstance(loc, tuple) and len(loc) >= 3:
        # Prefer pytest's relative path / domain; override lineno only.
        report.location = (loc[0], zero_based, loc[2])
    else:
        report.location = (path, zero_based, _func)
    return site
