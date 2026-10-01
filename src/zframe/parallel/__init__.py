"""Run the same pytest suite against multiple env targets in parallel.

Each device / lab unit is a separate ``config/env/<name>.yaml`` and gets its own
subprocess (one ``--env`` per process). Exit code is the worst child status.

Examples::

    python -m zframe.parallel --envs dev,env-b,env-c -- \\
        pytest . -q --config-dir ./config

    python -m zframe.parallel --all-envs --config-dir ./config -- \\
        pytest . -q

    zframe-parallel --envs dev,env-c --jobs 2 -- pytest -q
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from zframe.config.loader import discover_envs


@dataclass(frozen=True)
class EnvRunResult:
    env: str
    returncode: int
    command: tuple[str, ...]


def _parse_envs(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def resolve_target_envs(
    *,
    envs: Sequence[str] | None = None,
    all_envs: bool = False,
    config_dir: str | Path | None = None,
) -> list[str]:
    """Resolve which env names to run.

    Priority: explicit ``envs`` > ``all_envs`` (discover under config_dir).
    """
    explicit = [e for e in (envs or []) if e]
    if explicit:
        return list(dict.fromkeys(explicit))
    if not all_envs:
        raise ValueError("Specify --envs NAME[,NAME...] or --all-envs")
    if config_dir is None:
        raise ValueError("--all-envs requires --config-dir")
    found = discover_envs(config_dir)
    if not found:
        raise FileNotFoundError(f"No env YAML files under {Path(config_dir) / 'env'}")
    return found


def build_pytest_command(
    env: str,
    pytest_args: Sequence[str],
    *,
    config_dir: str | Path | None = None,
    python: str | None = None,
) -> list[str]:
    """Build ``python -m pytest ... --env <env>`` (injects --env / --config-dir)."""
    exe = python or sys.executable
    args = list(pytest_args)
    if not args:
        args = ["-m", "pytest"]
    elif args[0] in ("pytest", "py.test"):
        args = ["-m", "pytest", *args[1:]]
    elif args[0] != "-m":
        # Treat as pytest args: ``-q path`` → ``python -m pytest -q path``
        args = ["-m", "pytest", *args]

    cmd = [exe, *args]
    if "--env" not in cmd:
        cmd.extend(["--env", env])
    if config_dir is not None and "--config-dir" not in cmd:
        cmd.extend(["--config-dir", str(config_dir)])
    return cmd


def run_env(
    env: str,
    pytest_args: Sequence[str],
    *,
    config_dir: str | Path | None = None,
    cwd: str | Path | None = None,
) -> EnvRunResult:
    cmd = build_pytest_command(env, pytest_args, config_dir=config_dir)
    env_vars = os.environ.copy()
    env_vars["ZFRAME_PARALLEL_ENV"] = env
    print(f"[zframe.parallel] start env={env}: {' '.join(cmd)}", flush=True)
    completed = subprocess.run(cmd, cwd=cwd, env=env_vars)
    print(
        f"[zframe.parallel] done  env={env}: exit={completed.returncode}",
        flush=True,
    )
    return EnvRunResult(env=env, returncode=int(completed.returncode), command=tuple(cmd))


def run_parallel(
    envs: Sequence[str],
    pytest_args: Sequence[str],
    *,
    config_dir: str | Path | None = None,
    jobs: int | None = None,
    cwd: str | Path | None = None,
) -> list[EnvRunResult]:
    targets = list(envs)
    if not targets:
        raise ValueError("No envs to run")
    workers = max(1, min(jobs or len(targets), len(targets)))
    results: list[EnvRunResult] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                run_env,
                env,
                pytest_args,
                config_dir=config_dir,
                cwd=cwd,
            ): env
            for env in targets
        }
        for fut in as_completed(futures):
            results.append(fut.result())
    # Stable summary order matching request order
    by_env = {r.env: r for r in results}
    return [by_env[e] for e in targets]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zframe-parallel",
        description="Run pytest once per env target, in parallel subprocesses.",
    )
    parser.add_argument(
        "--envs",
        default=None,
        help="Comma-separated env names (config/env/<name>.yaml)",
    )
    parser.add_argument(
        "--all-envs",
        action="store_true",
        help="Discover and run every env under --config-dir/env/",
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        help="Config directory (forwarded to each pytest; required for --all-envs)",
    )
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=None,
        help="Max parallel env processes (default: number of envs)",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Pytest invocation after `--` (e.g. pytest path -q, or just path -q)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    pytest_args = list(args.pytest_args)
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]

    try:
        targets = resolve_target_envs(
            envs=_parse_envs(args.envs),
            all_envs=bool(args.all_envs),
            config_dir=args.config_dir,
        )
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))

    print(f"[zframe.parallel] targets: {', '.join(targets)}", flush=True)
    results = run_parallel(
        targets,
        pytest_args,
        config_dir=args.config_dir,
        jobs=args.jobs,
    )
    print("[zframe.parallel] summary:", flush=True)
    worst = 0
    for r in results:
        status = "OK" if r.returncode == 0 else f"FAIL({r.returncode})"
        print(f"  - {r.env}: {status}", flush=True)
        if r.returncode > worst:
            worst = r.returncode
    return worst
