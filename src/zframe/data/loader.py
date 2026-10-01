"""Load case data from JSON files (YAML kept as legacy fallback)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

# Prefer JSON; YAML/YML remain for backward compatibility.
_SUFFIXES = (".json", ".yaml", ".yml")


def _read_file(file_path: Path) -> Any:
    text = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    raise ValueError(f"Unsupported case file type: {file_path.suffix}")


def _as_case_list(value: Any, *, path: Path, label: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict) and isinstance(value.get("cases"), list):
        value = value["cases"]
    if not isinstance(value, list):
        raise ValueError(f"Cases for {label!r} must be a list in {path}")
    for idx, case in enumerate(value):
        if not isinstance(case, dict):
            raise ValueError(f"Case #{idx} under {label!r} must be a mapping in {path}")
    return value


def _find_named_ancestor(path: Path, name: str) -> Path | None:
    for parent in path.parents:
        if parent.name == name:
            return parent
    return None


def resolve_data_path(module_file: str | Path) -> Path:
    """Find data file whose stem matches the test module stem.

    Nested modules keep ``testcases/`` and ``testdata/`` as siblings. For example
    ``acme/WEB/API/Sample/testcases/test_sample.py`` resolves to
    ``acme/WEB/API/Sample/testdata/test_sample.json``.

    Search order (``.json`` preferred, then ``.yaml`` / ``.yml``):

    1. ``<module>/testdata/<relpath>.*`` (sibling of the enclosing ``testcases/``;
       ``data/`` as legacy)
    2. ``<case_dir>/testdata/<stem>.*`` (``data/`` as legacy)
    3. ``<case_dir>/<stem>.*`` (alongside the test module)
    """
    module_path = Path(module_file).resolve()
    stem = module_path.stem
    case_dir = module_path.parent
    bases: list[Path] = []

    testcases_root = _find_named_ancestor(module_path, "testcases")
    if testcases_root is not None:
        product_root = testcases_root.parent
        rel = module_path.relative_to(testcases_root).with_suffix("")
        bases.extend(
            (
                product_root / "testdata" / rel,
                product_root / "data" / rel,
            )
        )
    else:
        product_root = module_path.parent.parent
        bases.extend(
            (
                product_root / "testdata" / stem,
                product_root / "data" / stem,
            )
        )

    bases.extend(
        (
            case_dir / "testdata" / stem,
            case_dir / "data" / stem,
            case_dir / stem,
        )
    )

    tried: list[Path] = []
    for base in bases:
        for suffix in _SUFFIXES:
            candidate = base.parent / f"{base.name}{suffix}"
            tried.append(candidate)
            if candidate.is_file():
                return candidate
    locations = ", ".join(str(p) for p in tried)
    raise FileNotFoundError(
        f"No data file matching {stem!r} for {module_path}. Tried: {locations}"
    )


def select_cases(
    data: Any,
    *,
    path: Path,
    method: str,
    qualname: str | None = None,
    key: str | None = None,
) -> list[dict[str, Any]]:
    """Pick a case list from loaded data by explicit key or method/class name."""
    if data is None:
        return []

    if isinstance(data, list):
        if key is not None:
            raise ValueError(f"Cannot select key {key!r} from a top-level list in {path}")
        return _as_case_list(data, path=path, label="<root>")

    if not isinstance(data, dict):
        raise ValueError(f"Case file must be a list or mapping: {path}")

    if key is not None:
        if key not in data:
            raise KeyError(f"Key {key!r} not found in {path}")
        return _as_case_list(data[key], path=path, label=key)

    candidates: list[str] = []
    if qualname and qualname != method:
        candidates.append(qualname)
    candidates.append(method)

    for candidate in candidates:
        if candidate in data:
            return _as_case_list(data[candidate], path=path, label=candidate)

    if qualname and "." in qualname:
        class_name, method_name = qualname.rsplit(".", 1)
        nested = data.get(class_name)
        if isinstance(nested, dict) and method_name in nested:
            return _as_case_list(
                nested[method_name],
                path=path,
                label=f"{class_name}.{method_name}",
            )

    if isinstance(data.get("cases"), list):
        return _as_case_list(data["cases"], path=path, label="cases")

    looked = ", ".join(repr(c) for c in candidates)
    raise KeyError(f"No cases for method {method!r} (tried {looked}) in {path}")


def load_cases(
    path: str | Path,
    *,
    root: str | Path | None = None,
    key: str | None = None,
    method: str | None = None,
    qualname: str | None = None,
) -> list[dict[str, Any]]:
    """Load a list of case dicts from ``.json`` (or legacy ``.yaml`` / ``.yml``).

    Accepts:

    - a top-level list
    - a mapping with a ``cases`` key
    - a mapping keyed by test method name (or ``ClassName.test_method`` /
      nested ``ClassName: { test_method: [...] }``)
    """
    file_path = Path(path)
    if not file_path.is_absolute() and root is not None:
        file_path = Path(root) / file_path
    if not file_path.exists():
        raise FileNotFoundError(f"Case file not found: {file_path}")

    data = _read_file(file_path)
    if method is not None or key is not None:
        return select_cases(
            data,
            path=file_path,
            method=method or "",
            qualname=qualname,
            key=key,
        )
    if data is None:
        return []
    if isinstance(data, list):
        return _as_case_list(data, path=file_path, label="<root>")
    if isinstance(data, dict) and isinstance(data.get("cases"), list):
        return _as_case_list(data["cases"], path=file_path, label="cases")
    raise ValueError(
        f"Case file must be a list or {{cases: [...]}} "
        f"(or pass method=/key= for method-keyed files): {file_path}"
    )
