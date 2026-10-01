"""Generate a neutral case-layer repository from in-package templates."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from zframe.scaffold.templates import render_files

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ScaffoldError(Exception):
    """Invalid scaffold request."""


@dataclass(frozen=True)
class ScaffoldResult:
    dest: Path
    package: str


def derive_package_name(name: str) -> str:
    """Derive a Python package / auth.type name from ``--name``.

    ``acme-api-auto`` → ``acme``; invalid first segment falls back to full sanitize.
    """
    raw = (name or "").strip().lower().replace("-", "_")
    if not raw:
        raise ScaffoldError("Invalid --name: empty repository name")

    first = raw.split("_", 1)[0]
    if _IDENT_RE.match(first):
        return first

    if _IDENT_RE.match(raw):
        return raw

    safe = re.sub(r"[^a-z0-9_]", "_", raw)
    safe = re.sub(r"_+", "_", safe).strip("_")
    if not safe:
        raise ScaffoldError(f"Cannot derive package name from {name!r}")
    if not _IDENT_RE.match(safe):
        safe = f"p_{safe}"
    return safe


def scaffold_case_repo(
    *,
    dest: Path,
    force: bool = False,
) -> ScaffoldResult:
    """Write a generated case-repo tree to ``dest``."""
    dest = dest.expanduser().resolve()
    if not dest.name or dest.name in (".", ".."):
        raise ScaffoldError("Invalid --name: empty repository name")

    package = derive_package_name(dest.name)

    if dest.exists():
        if not force:
            raise ScaffoldError(
                f"Destination already exists: {dest} (pass --force to overwrite)"
            )
        if dest.is_file():
            raise ScaffoldError(f"Destination is a file, not a directory: {dest}")
        shutil.rmtree(dest)

    files = render_files(package=package)
    for rel, content in files.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    return ScaffoldResult(dest=dest, package=package)
