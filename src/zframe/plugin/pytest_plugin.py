"""pytest plugin: CLI options, session fixtures, HTML report attachments."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Generator

import pytest

from zframe.auth.base import AuthProvider
from zframe.auth.factory import build_auth
from zframe.client.http import HttpClient
from zframe.client.retry import RetryConfig
from zframe.config.loader import discover_config_root, load_settings
from zframe.config.models import Settings
from zframe.context.runtime import Context
from zframe.context.session import bind_session, clear_session, get_settings
from zframe.db.client import DbClient
from zframe.db.session import bind_db, clear_db
from zframe.ssh.client import SshClient
from zframe.ssh.session import bind_ssh, clear_ssh
from zframe.assertx.defaults import bind_assert_settings, reset_assert_settings
from zframe.notify.factory import build_notifier
from zframe.notify.summary import collect_run_summary, render_title, should_notify
from zframe.plugin.case_marks import (
    register_case_markers,
    resolve_case_meta,
    user_properties_for_meta,
    warn_duplicate_priorities,
)
from zframe.plugin.device_filter import deselect_for_env
from zframe.report.archive import (
    DEFAULT_REPORT_ROOT,
    finalize_report_archive,
    prepare_html_report,
)
from zframe.report.from_report import (
    FromReportError,
    deselect_not_in_report,
    extract_failed_nodeids,
    unmatched_wanted,
)
from zframe.report.capture import (
    bind_test_item,
    get_remembered_response,
    remember_response,
    reset_test_item,
)
from zframe.report.html_utils import (
    extras_for_response,
    pop_html_extras,
    pop_steps,
    render_case_detail_html,
    render_title_cell_html,
)

from zframe.report.logging import (
    LOG_FORMAT,
    enable_pytest_logging,
    get_logger,
    setup_logging,
)

from zframe.assertx.checkers import AssertionErrorX
from zframe.assertx.site import (
    apply_case_failure_location,
    format_call_failure,
    format_failure_at,
    resolve_case_failure_site,
    should_compact_call_failures,
)

# Before any get_logger(): avoid StreamHandler→stdout (duplicates Captured log + Win mojibake).
enable_pytest_logging()
logger = get_logger("zframe.plugin")

# Live terminal logs at INFO via pytest log_cli; report keeps Captured log (not stdout).
_DEFAULT_LOG_CLI_LEVEL = "INFO"
_DEFAULT_LOG_REPORT_LEVEL = "INFO"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("zframe")
    group.addoption(
        "--env",
        action="store",
        default=None,
        help="Target environment / device name (matches config/env/<name>.yaml; auto-discovered)",
    )
    group.addoption("--product", action="store", default=None, help="Product name")
    group.addoption(
        "--config-dir",
        action="store",
        default=None,
        help="Path to config directory (contains product.yaml and env/)",
    )
    group.addoption(
        "--report",
        action="store_true",
        dest="zframe_report",
        default=False,
        help="Write a self-contained HTML report under reports/<env>/<timestamp>/ (requires pytest-html)",
    )
    group.addoption(
        "--report-dir",
        action="store",
        dest="zframe_report_dir",
        default=DEFAULT_REPORT_ROOT,
        help=f"Root directory for archived HTML reports (default: {DEFAULT_REPORT_ROOT})",
    )
    group.addoption(
        "--notify",
        action="store_true",
        dest="zframe_notify",
        default=False,
        help="Enable session-end Feishu notify when notify.webhook is set (default off for local/dev)",
    )
    group.addoption(
        "--no-notify",
        action="store_true",
        dest="zframe_no_notify",
        default=False,
        help="Disable session-end notification even if notify.enabled is true in YAML",
    )
    group.addoption(
        "--no-live-log",
        action="store_true",
        dest="zframe_no_live_log",
        default=False,
        help="Disable zframe default live terminal logging (pytest log_cli at INFO)",
    )
    group.addoption(
        "--from-report",
        action="store",
        dest="zframe_from_report",
        default=None,
        metavar="PATH",
        help=(
            "Re-run only Failed/Error cases from a pytest-html report.html "
            "(or a run directory containing report.html)"
        ),
    )


def _configure_pytest_logging_defaults(config: pytest.Config) -> None:
    """Terminal live logs + report ``Captured log``; never duplicate via stdout.

    - ``log_cli``: IDE/CLI see INFO in real time (capture suspended while writing).
    - ``log_level``: INFO still lands in HTML ``Captured log`` (Unicode-safe).
    - No ``StreamHandler(sys.stdout)`` under pytest → no ``Captured stdout`` / Win mojibake.
    User CLI/ini overrides win.
    """
    if not getattr(config.option, "zframe_no_live_log", False):
        # Enabling --log-cli-level turns on live logging (_log_cli_enabled).
        if config.getoption("log_cli_level") is None and not config.getini("log_cli"):
            config.option.log_cli_level = _DEFAULT_LOG_CLI_LEVEL
        if config.getoption("log_cli_format") is None and not config.getini("log_cli_format"):
            config.option.log_cli_format = LOG_FORMAT

    # Ensure INFO zframe logs appear in report ``Captured log`` (not only live CLI).
    if config.getoption("log_level") is None and not config.getini("log_level"):
        config.option.log_level = _DEFAULT_LOG_REPORT_LEVEL


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    enable_pytest_logging()
    setup_logging()
    # Must run before pytest's LoggingPlugin (trylast) reads options.
    _configure_pytest_logging_defaults(config)
    config.addinivalue_line("markers", "zframe: mark test as zframe API test")
    config.addinivalue_line(
        "markers",
        "device(*names): run only when --env matches one of the given device/env names",
    )
    register_case_markers(config)
    if getattr(config.option, "zframe_report", False) and not hasattr(config.option, "htmlpath"):
        logger.warning(
            "--report requested but pytest-html is not installed; "
            "install with: pip install 'zframe[html]' or pip install pytest-html"
        )
        return
    env = _resolve_active_env(config)
    path = prepare_html_report(config, env=env)
    if path is not None:
        logger.info("html report -> %s", path)


def _resolve_active_env(config: pytest.Config) -> str | None:
    """Best-effort env name for device-marker filtering / report paths."""
    try:
        config_dir = resolve_config_dir(config)
        settings = load_settings(
            product=config.getoption("--product"),
            env=config.getoption("--env"),
            config_dir=config_dir,
        )
        return settings.env
    except Exception as exc:
        logger.debug("could not resolve env: %s", exc)
        explicit = config.getoption("--env", default=None)
        return str(explicit) if explicit else None


def pytest_collection_modifyitems(
    session: pytest.Session,
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    warn_duplicate_priorities(items)
    env = _resolve_active_env(config)
    if env:
        kept, deselected = deselect_for_env(items, env)
        if deselected:
            config.hook.pytest_deselected(items=deselected)
            items[:] = kept
            logger.info(
                "device filter: env=%s deselected %d test(s)",
                env,
                len(deselected),
            )
    _apply_from_report_filter(config, items)


def _apply_from_report_filter(config: pytest.Config, items: list[pytest.Item]) -> None:
    report_path = getattr(config.option, "zframe_from_report", None)
    if not report_path:
        return
    try:
        wanted = extract_failed_nodeids(report_path)
        kept, deselected = deselect_not_in_report(items, wanted)
    except FromReportError as exc:
        pytest.exit(str(exc), returncode=2)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept
    missing = unmatched_wanted(wanted, kept)
    if missing:
        sample = ", ".join(missing[:5])
        more = "" if len(missing) <= 5 else f" (+{len(missing) - 5} more)"
        logger.warning(
            "from-report: %d failed/error nodeid(s) not in collection: %s%s",
            len(missing),
            sample,
            more,
        )
    logger.info(
        "from-report: keeping %d / %d collected test(s) from %s",
        len(kept),
        len(kept) + len(deselected),
        report_path,
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config._zframe_session_start = time.time()  # type: ignore[attr-defined]
    # Must run before pytest-html (trylast) snapshots Environment into the report.
    _apply_html_environment(session.config)


def _resolve_base_url(config: pytest.Config) -> str:
    """Best-effort ``http.base_url`` for the HTML Environment section."""
    cached = getattr(config, "_zframe_settings", None)
    if isinstance(cached, Settings):
        return str(cached.http.base_url or "").strip()
    try:
        settings = load_settings(
            product=config.getoption("--product"),
            env=config.getoption("--env"),
            config_dir=resolve_config_dir(config),
        )
        return str(settings.http.base_url or "").strip()
    except Exception as exc:
        logger.debug("could not resolve base_url for report env: %s", exc)
        return ""


def _apply_html_environment(config: pytest.Config) -> None:
    """Keep HTML Environment minimal: only ``base_url`` (drop Python/Platform/Plugins…)."""
    try:
        from pytest_metadata.plugin import metadata_key
    except ImportError:
        return
    try:
        meta = config.stash[metadata_key]
    except KeyError:
        return
    meta.clear()
    base_url = _resolve_base_url(config)
    if base_url:
        meta["base_url"] = base_url


def _resolve_notify_settings(session: pytest.Session) -> Settings | None:
    """Prefer settings stashed on config; fall back to session bind / reload."""
    cached = getattr(session.config, "_zframe_settings", None)
    if isinstance(cached, Settings):
        return cached
    try:
        return get_settings()
    except Exception:
        pass
    try:
        config_dir = resolve_config_dir(session.config)
        return load_settings(
            product=session.config.getoption("--product"),
            env=session.config.getoption("--env"),
            config_dir=config_dir,
        )
    except Exception as exc:
        logger.warning("notify: could not load settings: %s", exc)
        return None


def _dispatch_notify(session: pytest.Session, exitstatus: int, run_dir: Path | None) -> None:
    if getattr(session.config.option, "zframe_no_notify", False):
        return

    settings = _resolve_notify_settings(session)
    if settings is None:
        return

    notify = settings.notify
    force = bool(getattr(session.config.option, "zframe_notify", False))
    if force and notify.webhook.strip():
        # CLI --notify overrides enabled=false when webhook is present.
        notify = notify.model_copy(update={"enabled": True})
    elif not notify.configured:
        return

    if not should_notify(on=notify.on, exitstatus=exitstatus):
        return

    try:
        notifier = build_notifier(notify)
    except Exception as exc:
        logger.warning("notify: build failed: %s", exc)
        return
    if notifier is None:
        return

    title = render_title(notify.title, product=settings.product, env=settings.env)
    start = getattr(session.config, "_zframe_session_start", None)
    duration_s = max(0.0, time.time() - float(start)) if start is not None else None
    summary = collect_run_summary(
        session,
        product=settings.product,
        env=settings.env,
        report_dir=run_dir,
        title=title,
        duration_s=duration_s,
    )
    try:
        notifier.send(summary)
    except Exception as exc:
        logger.warning("notify: send failed: %s", exc)


@pytest.hookimpl(hookwrapper=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int):
    # Yield so pytest-html (trylast) writes report.html before we polish / archive.
    yield
    run_dir = finalize_report_archive(session.config)
    if run_dir is not None:
        logger.info("html report archived at %s", run_dir)
    _dispatch_notify(session, exitstatus, run_dir)


def _path_from_nodeid_arg(arg: str) -> Path:
    raw = str(arg).split("::", 1)[0]
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def resolve_config_dir(pytestconfig: pytest.Config) -> Path | None:
    """Resolve config dir: CLI flag, then walk up from test args / cwd / rootpath."""
    explicit = pytestconfig.getoption("--config-dir")
    if explicit:
        return Path(explicit).resolve()

    starts: list[Path] = []
    for arg in pytestconfig.args:
        path = _path_from_nodeid_arg(arg)
        starts.append(path if path.is_dir() or not path.suffix else path.parent)
        # Even if the leaf does not exist yet, parents may contain config/
        starts.append(path.parent)

    starts.append(Path.cwd())
    starts.append(Path(pytestconfig.rootpath))

    seen: set[Path] = set()
    for start in starts:
        try:
            start = start.resolve()
        except OSError:
            continue
        if start in seen:
            continue
        seen.add(start)
        found = discover_config_root(start)
        if found is not None:
            return found
    return None


@pytest.fixture(scope="session")
def zframe_settings(pytestconfig: pytest.Config) -> Settings:
    env = pytestconfig.getoption("--env")
    product = pytestconfig.getoption("--product")
    config_dir = resolve_config_dir(pytestconfig)
    return load_settings(product=product, env=env, config_dir=config_dir)


@pytest.fixture(scope="session")
def zframe_ctx(zframe_settings: Settings) -> Context:
    ctx = Context(
        product=zframe_settings.product,
        env=zframe_settings.env,
        initial=zframe_settings.vars,
    )
    ctx.set("product", zframe_settings.product)
    ctx.set("env", zframe_settings.env)
    return ctx


@pytest.fixture(scope="session", autouse=True)
def _zframe_bind_session(
    zframe_settings: Settings,
    zframe_ctx: Context,
    pytestconfig: pytest.Config,
):
    """Inject once so cases can call ``get_settings()`` / ``get_ctx()`` without params."""
    bind_session(zframe_settings, zframe_ctx)
    pytestconfig._zframe_settings = zframe_settings  # type: ignore[attr-defined]
    try:
        yield
    finally:
        clear_session()


@pytest.fixture(scope="session")
def auth_provider(zframe_settings: Settings) -> AuthProvider:
    """Built from ``settings.auth`` via framework registry; override only for one-offs."""
    return build_auth(zframe_settings)


@pytest.fixture(scope="session")
def http_client(
    zframe_settings: Settings,
    auth_provider: AuthProvider,
) -> Generator[HttpClient, None, None]:
    http = zframe_settings.http
    client = HttpClient(
        base_url=http.base_url,
        headers=http.default_headers,
        timeout=http.timeout,
        verify=http.verify_ssl,
        auth=auth_provider,
        retry=RetryConfig(
            max_retries=http.max_retries,
            backoff_factor=http.retry_backoff,
        ),
    )
    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="session", autouse=True)
def zframe_ssh(zframe_settings: Settings) -> Generator[SshClient | None, None, None]:
    """Session SSH client when ``settings.ssh`` is configured; otherwise ``None``."""
    if not zframe_settings.ssh.enabled:
        bind_ssh(None)
        yield None
        return
    client = SshClient(zframe_settings.ssh)
    bind_ssh(client)
    try:
        yield client
    finally:
        clear_ssh()


@pytest.fixture(scope="session", autouse=True)
def zframe_db(
    zframe_settings: Settings,
    zframe_ssh: SshClient | None,
) -> Generator[DbClient | None, None, None]:
    """Session DB client when ``settings.db`` is configured; otherwise ``None``."""
    if not zframe_settings.db.enabled:
        bind_db(None)
        yield None
        return
    ssh = zframe_ssh
    client = DbClient(zframe_settings.db, ssh=ssh)
    bind_db(client)
    try:
        yield client
    finally:
        clear_db()


# Friendly aliases commonly used in case repos
@pytest.fixture(scope="session")
def settings(zframe_settings: Settings) -> Settings:
    return zframe_settings

@pytest.fixture(autouse=True)
def _zframe_bind_assert_settings(zframe_settings: Settings):
    """Bind ``settings.assertx`` so ``check(resp).body(...)`` picks up global defaults."""
    token = bind_assert_settings(zframe_settings.assertx)
    try:
        yield
    finally:
        reset_assert_settings(token)


@pytest.fixture(autouse=True)
def _zframe_bind_test_item(request: pytest.FixtureRequest):
    """Bind the active item so ``HttpClient`` can auto-remember the last response."""
    token = bind_test_item(request.node)
    remember_response(request.node, None)
    try:
        yield
    finally:
        reset_test_item(token)


@pytest.fixture(scope="session")
def ctx(zframe_ctx: Context) -> Context:
    return zframe_ctx


@pytest.fixture(scope="session")
def client(http_client: HttpClient) -> HttpClient:
    return http_client


@pytest.fixture(scope="session")
def db(zframe_db: DbClient | None) -> DbClient:
    """DB client for cases (requires ``db`` in env YAML)."""
    if zframe_db is None:
        raise RuntimeError(
            "DB is not configured; add a ``db`` section to config/env/<env>.yaml "
            "(and install PyMySQL via pip install 'zframe[db]')"
        )
    return zframe_db


@pytest.fixture(scope="session")
def ssh(zframe_ssh: SshClient | None) -> SshClient:
    """SSH client for cases (requires ``ssh`` in env YAML)."""
    if zframe_ssh is None:
        raise RuntimeError(
            "SSH is not configured; add an ``ssh`` section to config/env/<env>.yaml "
            "(and install paramiko via pip install 'zframe[ssh]')"
        )
    return zframe_ssh


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    """Attach case marks / steps after inner hooks (incl. pytest-html extras merge)."""
    outcome = yield
    report = outcome.get_result()

    if (
        report.failed
        and call.excinfo is not None
        and call.when == "call"
        and should_compact_call_failures(item.config.invocation_params.args)
    ):
        # Site + message only; no source dump / full traceback.
        # AssertionErrorX keeps its diff-first body; escape with explicit --tb=...
        exc = call.excinfo.value
        site = apply_case_failure_location(report, exc)
        report.longrepr = format_call_failure(exc, site)

    meta = resolve_case_meta(item, warn=False)
    # Visible on every phase row (setup/call/teardown) in the HTML table.
    report.zframe_case_id = meta.case_id  # type: ignore[attr-defined]
    report.zframe_case_title = meta.title  # type: ignore[attr-defined]
    report.zframe_priority = meta.priority or ""  # type: ignore[attr-defined]
    report.zframe_detail_html = ""  # type: ignore[attr-defined]

    # Stash hover-popup details for:
    # - call (pass or fail)
    # - failed setup/teardown (pytest-html only keeps those non-call rows)
    attach_details = report.when == "call" or (
        report.when in ("setup", "teardown") and report.failed
    )
    if not attach_details:
        return

    if meta.any and report.when == "call":
        props = list(getattr(report, "user_properties", None) or [])
        props.extend(user_properties_for_meta(meta))
        report.user_properties = props

    extras = pop_html_extras(item) if report.when == "call" else []
    steps = pop_steps(item) if report.when == "call" else []
    detail = render_case_detail_html(
        case_id=meta.case_id,
        title=meta.title,
        priority=meta.priority,
        steps=steps,
    )
    # Used by Title-column hover popup in pytest_html_results_table_row.
    report.zframe_detail_html = detail if (meta.any or steps) else ""  # type: ignore[attr-defined]

    if report.when == "call" and report.failed:
        response = get_remembered_response(item)
        if response is not None:
            extras.extend(extras_for_response(response, name="last_response"))

    if extras:
        report.extras = getattr(report, "extras", []) + extras


def pytest_exception_interact(
    node: pytest.Item | pytest.Collector,
    call: pytest.CallInfo[Any],
    report: Any,
) -> None:
    """Echo structured assertion diff to live log (after Captured log section)."""
    excinfo = call.excinfo
    if excinfo is None or not excinfo.errisinstance(AssertionErrorX):
        return
    site = resolve_case_failure_site(excinfo.value)
    logger.error("\n%s", format_failure_at(str(excinfo.value), site))


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_header(cells: list[str]) -> None:
    """Insert Case ID / Priority / Title columns so case text is visible without expanding."""
    cells.insert(2, '<th class="sortable" data-column-type="caseId">Case ID</th>')
    cells.insert(3, '<th class="sortable" data-column-type="priority">Priority</th>')
    cells.insert(4, '<th class="sortable" data-column-type="caseTitle">Title</th>')


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_row(report: Any, cells: list[str]) -> None:
    from html import escape

    case_id = escape(str(getattr(report, "zframe_case_id", "") or ""))
    priority = escape(str(getattr(report, "zframe_priority", "") or ""))
    title = str(getattr(report, "zframe_case_title", "") or "")
    detail = str(getattr(report, "zframe_detail_html", "") or "")
    cells.insert(2, f'<td class="col-caseId">{case_id}</td>')
    cells.insert(3, f'<td class="col-priority">{priority}</td>')
    cells.insert(4, render_title_cell_html(title=title, detail_html=detail))


# Re-export for ``from zframe import remember_response`` / rare manual use.
__all__ = ["remember_response", "resolve_config_dir"]
