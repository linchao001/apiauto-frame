"""pytest parametrize helpers for data-driven cases.

Default engine expands cases as ``meta_data`` / ``req`` / ``expect`` / ``test_data``.

When a product / case-repo needs a different JSON shape, either:

- pass ``passthrough=True`` with custom ``argname`` (one-off), or
- subclass :class:`Parametrize`, set ``default_argnames`` and override
  ``normalize_case`` / ``row_values`` / ``filter_cases``, then export an instance.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TypeVar, overload

import pytest

from zframe.data.loader import load_cases, resolve_data_path

F = TypeVar("F", bound=Callable[..., Any])

_ATTR = "__zframe_parametrize__"

# Default pytest params. ``req`` maps to normalized key ``request`` (pytest
# reserves the name ``request`` for FixtureRequest).
DEFAULT_ARGNAMES = ("meta_data", "req", "expect", "test_data")
_DEFAULT_ARG_FIELDS: dict[str, str] = {"req": "request"}
_CASE_BODY_KEYS = frozenset(
    {"meta_data", "req", "request", "expect", "response", "test_data"}
)


@dataclass(frozen=True)
class ParametrizeSpec:
    """Decoration options stored on a test function."""

    path: str | Path | None
    argname: str | Sequence[str]
    id_key: str
    root: str | Path | None
    key: str | None
    passthrough: bool
    engine: Parametrize


def _case_request(case: dict[str, Any]) -> dict[str, Any]:
    """Read request body; prefer ``req``, keep legacy ``request``."""
    return dict(case.get("req") or case.get("request") or {})


class Parametrize:
    """Data-driven parametrize engine.

    **Default** (``parametrize_from``): JSON ``meta_data`` / ``req`` / ``expect``
    / ``test_data`` → test params ``meta_data``, ``req``, ``expect``, ``test_data``.

    **Custom structure** — subclass and override hooks::

        class LoginParametrize(Parametrize):
            default_argnames = ("username", "password", "expect_code")
            passthrough = True

        parametrize_from = LoginParametrize()

    Or one-off without a subclass::

        @parametrize_from(argname="username,password,expect_code", passthrough=True)
        def test_login(username, password, expect_code):
            ...
    """

    #: Pytest parameter names injected by default for this engine.
    default_argnames: tuple[str, ...] = DEFAULT_ARGNAMES

    #: Map pytest param name → key in the (normalized) case dict.
    #: Default maps ``req`` → ``request`` so JSON can use ``req``.
    arg_fields: Mapping[str, str] = _DEFAULT_ARG_FIELDS

    #: When True, skip :meth:`normalize_case` and keep raw JSON objects.
    passthrough: bool = False

    def resolve_path(self, module_file: str | Path) -> Path:
        return resolve_data_path(module_file)

    def load_raw_cases(
        self,
        file_path: Path,
        *,
        method: str,
        qualname: str | None,
        key: str | None,
        root: str | Path | None,
    ) -> list[dict[str, Any]]:
        return load_cases(
            file_path,
            root=None if file_path.is_absolute() else root,
            key=key,
            method=method,
            qualname=qualname,
        )

    def normalize_case(self, case: dict[str, Any]) -> dict[str, Any]:
        """Normalize a raw case into ``meta_data`` / ``request`` / ``expect`` / ``test_data``.

        Override in a subclass (or use ``passthrough=True``) for other shapes.
        """
        request = _case_request(case)
        expect = dict(case.get("expect") or case.get("response") or {})
        test_data = dict(case.get("test_data") or {})
        if "meta_data" in case or "expect" in case:
            meta = dict(case.get("meta_data") or {})
            for key, value in case.items():
                if key not in _CASE_BODY_KEYS:
                    meta.setdefault(key, value)
        else:
            meta = {
                key: value
                for key, value in case.items()
                if key not in _CASE_BODY_KEYS
            }
        return {
            "meta_data": meta,
            "request": request,
            "expect": expect,
            "test_data": test_data,
        }

    def prepare_case(self, case: dict[str, Any], *, passthrough: bool) -> dict[str, Any]:
        """Turn one raw JSON object into the dict fed to :meth:`row_values`."""
        if passthrough:
            return dict(case)
        return self.normalize_case(case)

    def filter_cases(self, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Hook: drop or rewrite prepared cases before parametrize."""
        return cases

    def case_id(self, case: dict[str, Any], index: int, id_key: str) -> str:
        meta = case.get("meta_data") if isinstance(case.get("meta_data"), dict) else {}
        if id_key in meta and meta[id_key] is not None:
            return str(meta[id_key])
        if id_key in case and case[id_key] is not None:
            return str(case[id_key])
        for key in ("id", "case_id", "title", "name"):
            if key in meta and meta[key] is not None:
                return str(meta[key])
            if key in case and case[key] is not None:
                return str(case[key])
        return f"case_{index}"

    def parse_argnames(self, argname: str | Sequence[str]) -> tuple[str, ...]:
        if isinstance(argname, str):
            parts = [p.strip() for p in argname.split(",") if p.strip()]
            return tuple(parts) if parts else tuple(self.default_argnames)
        return tuple(argname) if argname else tuple(self.default_argnames)

    def row_values(self, case: dict[str, Any], argnames: tuple[str, ...]) -> tuple[Any, ...]:
        values: list[Any] = []
        for name in argnames:
            key = self.arg_fields.get(name, name)
            if key not in case:
                if name == "test_data":
                    values.append({})
                    continue
                raise KeyError(
                    f"Case is missing field {key!r} for param {name!r}; "
                    f"available keys: {sorted(case)}"
                )
            values.append(case[key])
        return tuple(values)

    def validate_argnames(self, argnames: tuple[str, ...], *, qualname: str) -> None:
        """Validate param names. Only ``request`` is always forbidden (pytest)."""
        if "request" in argnames:
            raise ValueError(
                f"{qualname}: parametrize arg name 'request' is reserved by pytest; "
                "use 'req' (or map via arg_fields) instead"
            )

    def bind(
        self,
        func: F,
        *,
        module_file: str | Path,
        method: str | None = None,
        qualname: str | None = None,
        path: str | Path | None = None,
        argname: str | Sequence[str] | None = None,
        id_key: str | None = None,
        root: str | Path | None = None,
        key: str | None = None,
        passthrough: bool | None = None,
    ) -> F:
        """Load cases and attach ``pytest.mark.parametrize`` to ``func``."""
        spec: ParametrizeSpec | None = getattr(func, _ATTR, None)
        path = path if path is not None else (spec.path if spec else None)
        argname = (
            argname
            if argname is not None
            else (spec.argname if spec else self.default_argnames)
        )
        id_key = id_key if id_key is not None else (spec.id_key if spec else "id")
        root = root if root is not None else (spec.root if spec else None)
        key = key if key is not None else (spec.key if spec else None)
        if passthrough is None:
            passthrough = spec.passthrough if spec is not None else self.passthrough
        method_name = method or func.__name__
        qname = qualname or func.__qualname__

        if path is not None:
            file_path = Path(path)
            if not file_path.is_absolute() and root is not None:
                file_path = Path(root) / file_path
        else:
            file_path = self.resolve_path(Path(module_file).resolve())

        raw_cases = self.load_raw_cases(
            file_path,
            method=method_name,
            qualname=qname,
            key=key,
            root=root,
        )
        cases = self.filter_cases(
            [self.prepare_case(case, passthrough=passthrough) for case in raw_cases]
        )
        argnames = self.parse_argnames(argname)
        self.validate_argnames(argnames, qualname=qname)

        ids = [self.case_id(case, i, id_key) for i, case in enumerate(cases)]
        values = [self.row_values(case, argnames) for case in cases]
        marked = pytest.mark.parametrize(",".join(argnames), values, ids=ids)(func)
        setattr(
            marked,
            _ATTR,
            ParametrizeSpec(
                path=path,
                argname=argname,
                id_key=id_key,
                root=root,
                key=key,
                passthrough=passthrough,
                engine=self,
            ),
        )
        return marked  # type: ignore[return-value]

    def decorate(
        self,
        func: F,
        *,
        path: str | Path | None = None,
        argname: str | Sequence[str] | None = None,
        id_key: str = "id",
        root: str | Path | None = None,
        key: str | None = None,
        passthrough: bool | None = None,
    ) -> F:
        resolved_argname: str | Sequence[str] = (
            argname if argname is not None else self.default_argnames
        )
        resolved_passthrough = self.passthrough if passthrough is None else passthrough
        setattr(
            func,
            _ATTR,
            ParametrizeSpec(
                path=path,
                argname=resolved_argname,
                id_key=id_key,
                root=root,
                key=key,
                passthrough=resolved_passthrough,
                engine=self,
            ),
        )
        return self.bind(
            func,
            module_file=inspect.getfile(func),
            method=func.__name__,
            qualname=func.__qualname__,
            path=path,
            argname=resolved_argname,
            id_key=id_key,
            root=root,
            key=key,
            passthrough=resolved_passthrough,
        )

    @overload
    def __call__(self, func: F) -> F: ...

    @overload
    def __call__(
        self,
        path: str | Path | None = None,
        *,
        argname: str | Sequence[str] | None = None,
        id_key: str = "id",
        root: str | Path | None = None,
        key: str | None = None,
        passthrough: bool | None = None,
    ) -> Callable[[F], F]: ...

    def __call__(
        self,
        path: str | Path | F | None = None,
        *,
        argname: str | Sequence[str] | None = None,
        id_key: str = "id",
        root: str | Path | None = None,
        key: str | None = None,
        passthrough: bool | None = None,
    ) -> F | Callable[[F], F]:
        """Decorator: load cases and expand with pytest parametrize.

        Path is optional (auto-resolve from test module + ``testdata/``).

        Use ``passthrough=True`` with custom ``argname`` when JSON keys should
        map 1:1 to test parameters (non-default structure).
        """
        if callable(path) and not isinstance(path, (str, Path)):
            return self.decorate(path)

        explicit_path = path

        def decorator(func: F) -> F:
            return self.decorate(
                func,
                path=explicit_path,  # type: ignore[arg-type]
                argname=argname,
                id_key=id_key,
                root=root,
                key=key,
                passthrough=passthrough,
            )

        return decorator


parametrize_from = Parametrize()
