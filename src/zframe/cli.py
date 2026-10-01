"""ZFrame command-line interface.

Examples::

    zframe --init --name acme-api-auto
    zframe --docs
    zframe --docs agent/http --open
    zframe -h
    python -m zframe --init --name acme-api-auto
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from typing import Sequence

from zframe.docs import DocsError, list_topics, resolve_docs_dir, resolve_topic
from zframe.scaffold.generator import ScaffoldError, scaffold_case_repo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zframe",
        description="ZFrame CLI - framework utilities for case-layer repos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "commands:\n"
            "  --init     Create a case-layer repository from framework templates\n"
            "  --docs     List docs; agents start with: zframe --docs agent\n"
            "\n"
            "examples:\n"
            "  zframe --init --name acme-api-auto\n"
            "  zframe --docs agent\n"
            "  zframe --docs agent/http\n"
            "  zframe --docs http\n"
            "\n"
            "related:\n"
            "  zframe-parallel   Run pytest once per env target in parallel\n"
            "  python -m zframe.parallel ...\n"
        ),
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize a case-layer repository in the current directory",
    )
    parser.add_argument(
        "--name",
        default=None,
        metavar="NAME",
        help="Case repository directory name (required with --init)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the destination directory if it already exists",
    )
    parser.add_argument(
        "--docs",
        nargs="?",
        const="",
        default=None,
        metavar="TOPIC",
        help="List bundled documentation topics, or show/open one topic",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="With --docs TOPIC, open the file in the default application",
    )
    return parser


def _run_docs(topic: str, *, open_file: bool) -> int:
    try:
        if topic == "":
            docs_dir = resolve_docs_dir()
            topics = list_topics()
            print(f"[zframe] docs: {docs_dir}", flush=True)
            for name in topics:
                print(f"  {name}", flush=True)
            if not topics:
                print("[zframe] (no topics found)", flush=True)
            return 0

        path = resolve_topic(topic)
        if open_file:
            opened = webbrowser.open(path.as_uri())
            if not opened:
                print(
                    f"[zframe] could not open {path}; path printed below",
                    file=sys.stderr,
                    flush=True,
                )
        print(str(path.resolve()), flush=True)
        return 0
    except DocsError as exc:
        print(f"[zframe] error: {exc}", file=sys.stderr, flush=True)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.docs is not None:
        if args.open and args.docs == "":
            parser.error("--open requires --docs TOPIC")
        return _run_docs(args.docs, open_file=bool(args.open))

    if not args.init:
        parser.print_help()
        return 0

    if not args.name or not str(args.name).strip():
        parser.error("--init requires --name NAME")

    name = str(args.name).strip()
    if Path(name).name != name or name in (".", ".."):
        parser.error("--name must be a single directory name (not a path)")

    dest = Path.cwd() / name
    try:
        result = scaffold_case_repo(
            dest=dest,
            force=bool(args.force),
        )
    except ScaffoldError as exc:
        print(f"[zframe] error: {exc}", file=sys.stderr, flush=True)
        return 1

    print(f"[zframe] initialized case repo: {result.dest}", flush=True)
    print(f"[zframe] package: {result.package}", flush=True)
    print(
        "[zframe] next:\n"
        f"  cd {result.dest.name}\n"
        "  pip install -e /path/to/ZFrame   # or: pip install zframe\n"
        "  pytest -q --env dev             # Sample uses httpbin + auth.type=none\n"
        "  # then implement ProductAuth and switch base_url / auth.type",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
