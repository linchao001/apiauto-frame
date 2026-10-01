"""pytest-html report archive helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from zframe.report.archive import (
    create_run_dir,
    html_path,
    polish_report_html,
    prepare_html_report,
    read_latest_run_dir,
    sanitize_env_segment,
    timestamp_run_id,
    write_latest_pointer,
)
from zframe.report.html_utils import (
    attach_text,
    extras_for_response,
    pop_html_extras,
    pop_steps,
    step,
)


class _FakeOption:
    def __init__(self, **kwargs):
        self.htmlpath = kwargs.get("htmlpath")
        self.self_contained_html = kwargs.get("self_contained_html", False)
        self.zframe_report = kwargs.get("zframe_report", False)
        self.zframe_report_dir = kwargs.get("zframe_report_dir", "reports")


class _FakeConfig:
    def __init__(self, **kwargs):
        self.option = _FakeOption(**kwargs)


class _FakeItem:
    pass


def test_timestamp_run_id_format():
    assert timestamp_run_id(datetime(2026, 8, 6, 9, 15, 30)) == "20260806_091530"


def test_sanitize_env_segment():
    assert sanitize_env_segment("dev") == "dev"
    assert sanitize_env_segment("../evil") == "evil"
    assert sanitize_env_segment("") == "default"
    assert sanitize_env_segment("a/b") == "b"


def test_create_run_dir_and_latest_pointer(tmp_path: Path):
    root = tmp_path / "reports"
    run = create_run_dir(root, env="dev", run_id="20260806_091530")
    assert run == root / "dev" / "20260806_091530"
    assert run.is_dir()
    assert html_path(run) == run / "report.html"

    write_latest_pointer(run.parent, run)
    latest = read_latest_run_dir(root, env="dev")
    assert latest == run.resolve()
    data = json.loads((root / "dev" / "latest.json").read_text(encoding="utf-8"))
    assert data["run_id"] == "20260806_091530"
    assert data["env"] == "dev"
    assert data["path"] == "20260806_091530"
    assert data["html"] == "report.html"


def test_prepare_html_report_archives_with_report_flag(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = _FakeConfig(
        htmlpath=None,
        zframe_report=True,
        zframe_report_dir=str(tmp_path / "reports"),
    )
    path = prepare_html_report(config, env="dev")
    assert path is not None
    assert path.name == "report.html"
    assert path.parent.parent.name == "dev"
    assert Path(config.option.htmlpath) == path
    assert config.option.self_contained_html is True
    assert read_latest_run_dir(tmp_path / "reports", env="dev") is not None


def test_prepare_html_report_noop_without_report_flag(tmp_path: Path):
    config = _FakeConfig(htmlpath=None, zframe_report=False)
    assert prepare_html_report(config, env="dev") is None
    assert config.option.htmlpath is None


def test_prepare_html_report_keeps_explicit_htmlpath(tmp_path: Path):
    explicit = tmp_path / "custom" / "out.html"
    explicit.parent.mkdir(parents=True)
    config = _FakeConfig(
        htmlpath=str(explicit),
        zframe_report=True,
        zframe_report_dir=str(tmp_path / "reports"),
    )
    assert prepare_html_report(config, env="dev") == explicit
    assert config.option.htmlpath == str(explicit)


def test_polish_report_html_chinese_timestamp(tmp_path: Path):
    path = tmp_path / "report.html"
    path.write_text(
        '<html><body><h1>t</h1>\n'
        '<p>Report generated on 19-Aug-2026 at 15:16:09 by '
        '<a href="https://pypi.python.org/pypi/pytest-html">pytest-html</a>\n'
        "        v4.2.0</p>\n</body></html>\n",
        encoding="utf-8",
    )
    assert polish_report_html(path, when=datetime(2026, 8, 19, 15, 16, 9)) is True
    text = path.read_text(encoding="utf-8")
    assert "报告生成时间：2026-08-19 15:16:09" in text
    assert "pytest-html" not in text
    assert "Report generated" not in text


def test_report_js_decodes_html_entities_in_logs():
    js = (Path(__file__).resolve().parents[1] / "src/zframe/report/resources/report.js").read_text(
        encoding="utf-8"
    )
    assert "decodeHtmlEntities" in js
    assert "decodeHtmlEntities(log" in js or "decodeHtmlEntities(log ||" in js
    """caseTitle embeds HTML; decoding via innerHTML corrupts the JSON blob."""
    js = (Path(__file__).resolve().parents[1] / "src/zframe/report/resources/report.js").read_text(
        encoding="utf-8"
    )
    assert "JSON.parse(raw)" in js
    assert "textarea.innerHTML = raw" not in js


def test_polish_report_html_injects_zframe_ui(tmp_path: Path):
    path = tmp_path / "report.html"
    path.write_text(
        "<html><head><title>r</title></head><body>\n"
        '<div class="summary"><h2>Summary</h2></div>\n'
        '<table id="results-table"></table>\n'
        '<div id="data-container" data-jsonblob="{}"></div>\n'
        '<p>Report generated on 19-Aug-2026 at 15:16:09 by '
        '<a href="https://pypi.python.org/pypi/pytest-html">pytest-html</a> '
        "v4.2.0</p>\n"
        "</body></html>\n",
        encoding="utf-8",
    )
    assert polish_report_html(path, when=datetime(2026, 8, 19, 15, 16, 9)) is True
    text = path.read_text(encoding="utf-8")
    assert 'id="zframe-report-ui"' in text
    assert 'id="zframe-report-ui-css"' in text
    assert 'id="zframe-report-ui-js"' in text
    assert "zframe-overview" in text
    assert "zframe-case-tree" in text
    assert "zframe-detail-steps" in text
    assert "zframe-detail-log" in text
    assert "zframe-env" in text
    # Idempotent: second polish must not duplicate shells.
    assert polish_report_html(path, when=datetime(2026, 8, 19, 15, 16, 9)) is True
    again = path.read_text(encoding="utf-8")
    assert again.count('id="zframe-report-ui"') == 1
    assert again.count('id="zframe-report-ui-js"') == 1


def test_html_extras_queue_and_response(monkeypatch):
    from zframe.report import capture

    item = _FakeItem()
    token = capture.bind_test_item(item)
    try:
        attach_text("hello", name="note")
        with step("do thing"):
            pass
        extras = pop_html_extras(item)
        names = [e.get("name") for e in extras]
        assert "note" in names
        assert pop_steps(item) == [("do thing", "ok")]
    finally:
        capture.reset_test_item(token)

    # extras_for_response does not need an active item
    class _Resp:
        def to_dict(self):
            return {"status_code": 200, "body": {"ok": True}}

    built = extras_for_response(_Resp(), name="last_response")  # type: ignore[arg-type]
    assert len(built) == 1
    assert built[0]["name"] == "last_response"
