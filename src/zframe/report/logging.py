"""Structured logging setup."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


_CONFIGURED = False

# Include lineno so wrappers need not put Lxx into the message.
# Call-site attribution: :class:`ZFrameLogger` skips registered origin files.
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s"

# Set by ``zframe.plugin.pytest_plugin`` when pytest loads the plugin.
# Do not use ``"pytest" in sys.modules``: importing zframe pulls in pytest via
# ``parametrize``, which would false-trigger and suppress stdout logging outside tests.
_PYTEST_FLAG = "_zframe_pytest_logging"

# Absolute, normcased paths skipped when attributing filename/lineno (case-repo helpers).
_ORIGIN_SKIP: set[str] = set()


def register_log_origin_skip(*paths: str | Path) -> None:
    """Skip these files when resolving log call-site (filename / lineno).

    Use in case-repo helper modules that wrap ``logger.info`` so the record
    points at the business call site, not the helper.
    """
    for path in paths:
        _ORIGIN_SKIP.add(os.path.normcase(os.path.abspath(str(path))))


def enable_pytest_logging() -> None:
    """Mark that we are running under pytest (no stdout StreamHandler)."""
    setattr(sys, _PYTEST_FLAG, True)


def _under_pytest() -> bool:
    return bool(getattr(sys, _PYTEST_FLAG, False))


def _is_stdout_stream_handler(handler: logging.Handler) -> bool:
    """True for plain StreamHandlers writing to stdout/stderr (not FileHandler)."""
    if type(handler) is not logging.StreamHandler:
        return False
    stream = getattr(handler, "stream", None)
    return stream in (sys.stdout, sys.stderr, getattr(sys, "__stdout__", None))


def _strip_stdout_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        if _is_stdout_stream_handler(handler):
            logger.removeHandler(handler)
            handler.close()


def _logging_srcfile() -> str | None:
    src = getattr(logging, "_srcfile", None)
    return os.path.normcase(src) if src else None


class ZFrameLogger(logging.Logger):
    """Logger that attributes call-site past registered helper / logging frames."""

    def findCaller(self, stack_info: bool = False, stacklevel: int = 1):
        f = logging.currentframe()
        if f is not None:
            f = f.f_back
        rv = "(unknown file)", 0, "(unknown function)", None
        srcfile = _logging_srcfile()
        while hasattr(f, "f_code"):
            co = f.f_code
            filename = os.path.normcase(co.co_filename)
            if filename == srcfile or filename in _ORIGIN_SKIP:
                f = f.f_back
                continue
            if stacklevel > 1:
                stacklevel -= 1
                f = f.f_back
                continue
            sinfo = None
            if stack_info:
                import io
                import traceback

                sio = io.StringIO()
                sio.write("Stack (most recent call last):\n")
                traceback.print_stack(f, file=sio)
                sinfo = sio.getvalue().rstrip("\n")
            rv = (co.co_filename, f.f_lineno, co.co_name, sinfo)
            break
        return rv


# New zframe.* loggers (and any created after import) use call-site skipping.
if not issubclass(logging.getLoggerClass(), ZFrameLogger):
    logging.setLoggerClass(ZFrameLogger)


def setup_logging(level: int | str = logging.INFO) -> None:
    """Configure the ``zframe`` logger.

    Under pytest, do **not** attach a ``StreamHandler`` to stdout/stderr.
    Live output uses pytest ``log_cli``; the same records are captured into report
    ``Captured log`` (Unicode-safe). Writing to stdout would also fill
    ``Captured stdout`` and mojibake Chinese on Windows (cp936 fd capture).
    """
    global _CONFIGURED
    root = logging.getLogger("zframe")
    root.setLevel(
        level if isinstance(level, int) else getattr(logging, str(level).upper(), logging.INFO)
    )
    root.propagate = False

    if _under_pytest():
        _strip_stdout_handlers(root)
        if not root.handlers:
            root.addHandler(logging.NullHandler())
        _CONFIGURED = True
        return

    if _CONFIGURED:
        return
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str = "zframe") -> logging.Logger:
    if not name.startswith("zframe"):
        name = f"zframe.{name}"
    setup_logging()
    return logging.getLogger(name)
