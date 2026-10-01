"""zframe logging: format + call-site attribution past helper wrappers."""

from __future__ import annotations

import importlib.util
import inspect
import logging
from pathlib import Path

from zframe.report.logging import LOG_FORMAT, ZFrameLogger


def test_log_format_includes_lineno() -> None:
    assert "%(lineno)d" in LOG_FORMAT


def test_origin_skip_attributes_lineno_to_caller(tmp_path: Path) -> None:
    proxy = tmp_path / "case_log_proxy.py"
    proxy.write_text(
        "from zframe import get_logger, register_log_origin_skip\n"
        "register_log_origin_skip(__file__)\n"
        "\n"
        "def emit(msg: str) -> None:\n"
        "    get_logger('test.origin_skip').info(msg)\n",
        encoding="utf-8",
    )

    spec = importlib.util.spec_from_file_location("case_log_proxy", proxy)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    records: list[logging.LogRecord] = []

    class ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    root = logging.getLogger("zframe")
    handler = ListHandler()
    root.addHandler(handler)
    try:
        mod.emit("hello")
        expected_lineno = inspect.currentframe().f_lineno - 1  # type: ignore[union-attr]
    finally:
        root.removeHandler(handler)

    assert records, "expected a log record"
    rec = records[-1]
    assert isinstance(logging.getLogger("zframe.test.origin_skip"), ZFrameLogger)
    assert rec.getMessage() == "hello"
    assert rec.lineno == expected_lineno
    assert Path(rec.pathname).resolve() == Path(__file__).resolve()
    # Proxy registration should have taken effect.
    assert any(
        Path(p).name == "case_log_proxy.py"
        for p in __import__("zframe.report.logging", fromlist=["_ORIGIN_SKIP"])._ORIGIN_SKIP
    )
