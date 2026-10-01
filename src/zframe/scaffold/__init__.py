"""Scaffold a case-layer repository from framework templates."""

from __future__ import annotations

from zframe.scaffold.generator import (
    ScaffoldError,
    ScaffoldResult,
    derive_package_name,
    scaffold_case_repo,
)

__all__ = [
    "ScaffoldError",
    "ScaffoldResult",
    "derive_package_name",
    "scaffold_case_repo",
]
