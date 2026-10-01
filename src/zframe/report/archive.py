"""Per-run pytest-html report archival under ``reports/<env>/<timestamp>/``."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_REPORT_ROOT = "reports"
LATEST_POINTER = "latest.json"
HTML_FILENAME = "report.html"
DEFAULT_ENV_SEGMENT = "default"
_RESOURCES = Path(__file__).resolve().parent / "resources"
REPORT_CSS = _RESOURCES / "report.css"
REPORT_JS = _RESOURCES / "report.js"

# pytest-html default footer (see resources/index.jinja2).
_PYTEST_HTML_GENERATED_RE = re.compile(
    r"<p>Report generated on .+? by "
    r'<a href="https://pypi\.python\.org/pypi/pytest-html">pytest-html</a>'
    r"\s*v[\d.]+</p>",
    re.DOTALL,
)
_ZFRAME_UI_STYLE_RE = re.compile(
    r'\s*<style[^>]*\bid="zframe-report-ui-css"[^>]*>.*?</style>',
    re.DOTALL | re.IGNORECASE,
)
_ZFRAME_UI_SCRIPT_RE = re.compile(
    r'\s*<script[^>]*\bid="zframe-report-ui-js"[^>]*>.*?</script>',
    re.DOTALL | re.IGNORECASE,
)
_ZFRAME_UI_DIV_RE = re.compile(
    r'\s*<div[^>]*\bid="zframe-report-ui"[^>]*>\s*</div>',
    re.IGNORECASE,
)


def _inject_zframe_ui(text: str) -> str:
    """Embed overview/master-detail CSS+JS shell (idempotent replace)."""
    css = REPORT_CSS.read_text(encoding="utf-8") if REPORT_CSS.is_file() else ""
    js = REPORT_JS.read_text(encoding="utf-8") if REPORT_JS.is_file() else ""

    cleaned = _ZFRAME_UI_STYLE_RE.sub("", text)
    cleaned = _ZFRAME_UI_SCRIPT_RE.sub("", cleaned)
    cleaned = _ZFRAME_UI_DIV_RE.sub("", cleaned)

    style_tag = (
        f'<style type="text/css" id="zframe-report-ui-css">\n{css}\n</style>\n'
    )
    if re.search(r"</head\s*>", cleaned, re.IGNORECASE):
        cleaned = re.sub(
            r"</head\s*>",
            style_tag + "</head>",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        cleaned = style_tag + cleaned

    body_inject = (
        '<div id="zframe-report-ui"></div>\n'
        f'<script id="zframe-report-ui-js">\n{js}\n</script>\n'
    )
    body_match = None
    for m in re.finditer(r"</body\s*>", cleaned, flags=re.IGNORECASE):
        body_match = m
    if body_match is not None:
        i = body_match.start()
        cleaned = cleaned[:i] + body_inject + cleaned[i:]
    else:
        cleaned = cleaned + body_inject
    return cleaned


def polish_report_html(path: Path | str, *, when: datetime | None = None) -> bool:
    """Localize footer and inject ZFrame overview / case-detail UI.

    Returns True when the report has the ZFrame UI shell (after rewrite).
    """
    html_file = Path(path)
    if not html_file.is_file():
        return False
    text = html_file.read_text(encoding="utf-8")
    stamp = (when or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    replacement = f"<p>报告生成时间：{stamp}</p>"
    new_text, _count = _PYTEST_HTML_GENERATED_RE.subn(replacement, text, count=1)
    new_text = _inject_zframe_ui(new_text)
    if new_text != text:
        html_file.write_text(new_text, encoding="utf-8")
    return 'id="zframe-report-ui"' in new_text


def timestamp_run_id(when: datetime | None = None) -> str:
    when = when or datetime.now()
    return when.strftime("%Y%m%d_%H%M%S")


def sanitize_env_segment(env: str | None) -> str:
    """Make an env name safe as a single path segment under ``reports/``."""
    raw = (env or "").strip()
    if not raw:
        return DEFAULT_ENV_SEGMENT
    # Drop any directory components (e.g. ``../x`` → ``x``).
    name = Path(raw.replace("\\", "/")).name.strip()
    if name in ("", ".", ".."):
        return DEFAULT_ENV_SEGMENT
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in name)
    return safe or DEFAULT_ENV_SEGMENT


def create_run_dir(
    report_root: Path | str,
    *,
    env: str | None = None,
    run_id: str | None = None,
) -> Path:
    """Create ``<report_root>/<env>/<run_id>/`` and return it."""
    root = Path(report_root)
    env_dir = root / sanitize_env_segment(env)
    run_dir = env_dir / (run_id or timestamp_run_id())
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def html_path(run_dir: Path | str) -> Path:
    return Path(run_dir) / HTML_FILENAME


def write_latest_pointer(pointer_root: Path | str, run_dir: Path | str) -> Path:
    """Write ``latest.json`` under ``pointer_root`` (typically ``reports/<env>/``)."""
    root = Path(pointer_root).resolve()
    run = Path(run_dir).resolve()
    try:
        rel = run.relative_to(root).as_posix()
    except ValueError:
        rel = str(run)
    pointer = root / LATEST_POINTER
    root.mkdir(parents=True, exist_ok=True)
    pointer.write_text(
        json.dumps(
            {
                "run_id": run.name,
                "env": root.name,
                "path": rel,
                "absolute": str(run),
                "html": HTML_FILENAME,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return pointer


def read_latest_run_dir(
    report_root: Path | str | None = None,
    *,
    env: str | None = None,
) -> Path | None:
    """Read ``latest.json`` under ``reports/<env>/`` (or legacy ``reports/latest.json``)."""
    root = Path(report_root or DEFAULT_REPORT_ROOT)
    if env is not None:
        pointer_root = root / sanitize_env_segment(env)
    elif (root / LATEST_POINTER).is_file():
        pointer_root = root
    else:
        pointer_root = root / DEFAULT_ENV_SEGMENT

    pointer = pointer_root / LATEST_POINTER
    if not pointer.is_file():
        return None
    data: dict[str, Any] = json.loads(pointer.read_text(encoding="utf-8"))
    rel = data.get("path") or data.get("run_id")
    if not rel:
        return None
    candidate = Path(rel)
    if not candidate.is_absolute():
        candidate = pointer_root / candidate
    return candidate if candidate.is_dir() else None


def _ensure_report_css(config: Any) -> None:
    """Append ZFrame report CSS so title hover popups are styled."""
    if not REPORT_CSS.is_file():
        return
    path = str(REPORT_CSS)
    existing = list(getattr(config.option, "css", None) or [])
    if path not in existing:
        existing.append(path)
    config.option.css = existing


def prepare_html_report(config: Any, *, env: str | None = None) -> Path | None:
    """When ``--report`` is set, archive under ``reports/<env>/<timestamp>/``."""
    if not getattr(config.option, "zframe_report", False):
        return None
    if not hasattr(config.option, "htmlpath"):
        return None

    report_root = Path(getattr(config.option, "zframe_report_dir", None) or DEFAULT_REPORT_ROOT)
    env_name = sanitize_env_segment(env)
    _ensure_report_css(config)

    if config.option.htmlpath:
        # Explicit ``--html``: still record archive metadata when under a run folder.
        path = Path(config.option.htmlpath)
        run_dir = path.parent
        pointer_root = run_dir.parent if run_dir.parent != run_dir else report_root / env_name
        config._zframe_report_run_dir = run_dir  # type: ignore[attr-defined]
        config._zframe_report_root = report_root  # type: ignore[attr-defined]
        config._zframe_report_pointer_root = pointer_root  # type: ignore[attr-defined]
        write_latest_pointer(pointer_root, run_dir)
        return path

    run_dir = create_run_dir(report_root, env=env_name)
    path = html_path(run_dir)
    config.option.htmlpath = str(path)
    # Offline single file: styles/scripts/images inlined.
    if hasattr(config.option, "self_contained_html"):
        config.option.self_contained_html = True
    pointer_root = run_dir.parent
    config._zframe_report_run_dir = run_dir  # type: ignore[attr-defined]
    config._zframe_report_root = report_root  # type: ignore[attr-defined]
    config._zframe_report_pointer_root = pointer_root  # type: ignore[attr-defined]
    write_latest_pointer(pointer_root, run_dir)
    return path


def finalize_report_archive(config: Any) -> Path | None:
    """Refresh latest pointer and polish HTML footer after pytest-html writes the file."""
    run_dir: Path | None = getattr(config, "_zframe_report_run_dir", None)
    if run_dir is None:
        return None
    pointer_root: Path | None = getattr(config, "_zframe_report_pointer_root", None)
    if pointer_root is None:
        pointer_root = run_dir.parent
    write_latest_pointer(pointer_root, run_dir)
    polish_report_html(html_path(run_dir))
    return run_dir
