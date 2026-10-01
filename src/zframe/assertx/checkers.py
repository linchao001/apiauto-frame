"""Functional assertions: HTTP response and generic value checks."""

from __future__ import annotations

from collections.abc import Sized
from typing import Any, Mapping, Sequence

import jsonschema
from jsonpath_ng import parse as jsonpath_parse

from zframe.assertx.compare import CompareMode, compare_values, merge_excludes
from zframe.assertx.defaults import get_assert_settings
from zframe.assertx.format import format_assertion_failure, format_plain_failure
from zframe.client.response import Response
from zframe.config.models import AssertSettings, Settings


class AssertionErrorX(AssertionError):
    """Assertion failure with optional response context and structured diffs."""

    def __init__(
        self,
        message: str = "",
        *,
        response: Response | None = None,
        label: str | None = None,
        diffs: list[str] | None = None,
        show_body_hint: bool = False,
    ) -> None:
        self.response = response
        self.label = label or ""
        self.diffs = list(diffs or [])
        self.show_body_hint = show_body_hint
        if label is not None and diffs is not None:
            self._message = format_assertion_failure(
                label,
                diffs,
                response=response,
                show_body_hint=show_body_hint,
            )
        elif message:
            self._message = (
                message
                if message.startswith("Assertion failed")
                else format_plain_failure(message)
            )
        else:
            self._message = format_plain_failure("assertion failed")
        super().__init__(self._message)

    def __str__(self) -> str:
        return self._message

    def compact_lines(self) -> list[str]:
        """One-line-per-diff summaries for soft assertion aggregation."""
        if not self.diffs:
            return [self._message.splitlines()[0]]
        if len(self.diffs) == 1:
            head = f"{self.label}: " if self.label else ""
            return [f"{head}{self.diffs[0]}"]
        lines = [f"{self.label}:"] if self.label else []
        lines.extend(f"  {item}" for item in self.diffs)
        return lines


def extract(data: Any, path: str, default: Any = None) -> Any:
    matches = [m.value for m in jsonpath_parse(path).find(data)]
    if not matches:
        return default
    return matches[0] if len(matches) == 1 else matches


class _AssertCfgMixin:
    """Shared assert-settings resolution for response and value checkers."""

    _settings: Settings | AssertSettings | None
    _response: Response | None = None

    def _assert_cfg(self) -> AssertSettings:
        if isinstance(self._settings, AssertSettings):
            return self._settings
        if isinstance(self._settings, Settings):
            return self._settings.assertx
        return get_assert_settings()

    def _resolve_cfg(self, settings: Settings | AssertSettings | None) -> AssertSettings:
        if isinstance(settings, AssertSettings):
            return settings
        if isinstance(settings, Settings):
            return settings.assertx
        return self._assert_cfg()

    def _resolve_compare_opts(
        self,
        *,
        mode: CompareMode | None,
        exclude: Sequence[str] | None,
        allow_extra: bool | None,
        settings: Settings | AssertSettings | None,
    ) -> tuple[CompareMode, bool, list[str]]:
        cfg = self._resolve_cfg(settings)
        resolved_mode: CompareMode = mode if mode is not None else cfg.mode
        resolved_extra = cfg.allow_extra if allow_extra is None else allow_extra
        if resolved_mode not in ("loose", "strict"):
            raise ValueError(f"Unsupported compare mode: {resolved_mode!r}")
        excludes = merge_excludes(cfg.exclude, exclude)
        return resolved_mode, resolved_extra, excludes

    @staticmethod
    def _fail_label(default: str, msg: str | None) -> str:
        return msg if msg else default

    @staticmethod
    def _plain_message(detail: str, msg: str | None) -> str:
        return f"{msg}: {detail}" if msg else detail

    def _raise_diffs(self, label: str, diffs: list[str], *, msg: str | None = None) -> None:
        raise AssertionErrorX(
            label=self._fail_label(label, msg),
            diffs=diffs,
            response=self._response,
        )


class _Check(_AssertCfgMixin):
    def __init__(self, response: Response, *, settings: Settings | AssertSettings | None = None) -> None:
        self.response = response
        self._response = response
        self._settings = settings

    def status(self, code: int, *, msg: str | None = None) -> _Check:
        actual = self.response.status_code
        if actual != code:
            raise AssertionErrorX(
                label=self._fail_label("HTTP status", msg),
                diffs=[f"status: expected {code}, got {actual}"],
                response=self.response,
                show_body_hint=True,
            )
        return self

    def status_in(self, *codes: int, msg: str | None = None) -> _Check:
        actual = self.response.status_code
        if actual not in codes:
            raise AssertionErrorX(
                label=self._fail_label("HTTP status", msg),
                diffs=[f"status: expected one of {list(codes)}, got {actual}"],
                response=self.response,
                show_body_hint=True,
            )
        return self

    def jsonpath(
        self,
        path: str,
        expected: Any = None,
        *,
        exists: bool = True,
        msg: str | None = None,
    ) -> _Check:
        """Assert a JSONPath value; ``expected`` supports the same matchers as ``body``.

        Matchers: ``ANY`` / ``Regex`` / ``Approx``, or JSON markers
        ``{"$any": true}`` / ``{"$regex": "..."}`` / ``{"$approx": 1.0, "abs": 0.01}``.
        Nested dict/list expectations use the same deep-compare rules as ``body``
        (default ``loose`` + ``allow_extra``).
        """
        value = self.response.extract(path, default=None)
        if exists and value is None:
            raise AssertionErrorX(
                self._plain_message(f"JSONPath not found: {path}", msg),
                response=self.response,
            )
        if expected is None:
            return self
        diffs = compare_values(value, expected, path=path)
        if diffs:
            self._raise_diffs(f"JSONPath {path} assertion failed", diffs, msg=msg)
        return self

    def contains(self, text: str, *, msg: str | None = None) -> _Check:
        if text not in self.response.text:
            raise AssertionErrorX(
                self._plain_message(f"Response text does not contain {text!r}", msg),
                response=self.response,
            )
        return self

    def schema(self, schema: Mapping[str, Any], *, msg: str | None = None) -> _Check:
        try:
            payload = self.response.json()
        except Exception as exc:
            raise AssertionErrorX(
                self._plain_message(f"Response is not JSON: {exc}", msg),
                response=self.response,
            ) from exc
        try:
            jsonschema.validate(instance=payload, schema=dict(schema))
        except jsonschema.ValidationError as exc:
            raise AssertionErrorX(
                self._plain_message(f"Schema validation failed: {exc.message}", msg),
                response=self.response,
            ) from exc
        return self

    def header(
        self,
        name: str,
        expected: str | None = None,
        *,
        msg: str | None = None,
    ) -> _Check:
        actual = self.response.headers.get(name)
        if actual is None:
            raise AssertionErrorX(
                self._plain_message(f"Header missing: {name}", msg),
                response=self.response,
            )
        if expected is not None and actual != expected:
            raise AssertionErrorX(
                label=self._fail_label(f"Header {name}", msg),
                diffs=[f"{name}: expected {expected!r}, got {actual!r}"],
                response=self.response,
            )
        return self

    def body(
        self,
        expected: Any,
        *,
        mode: CompareMode | None = None,
        exclude: Sequence[str] | None = None,
        allow_extra: bool | None = None,
        path: str | None = None,
        meta: Mapping[str, Any] | None = None,
        settings: Settings | AssertSettings | None = None,
        msg: str | None = None,
    ) -> _Check:
        """Assert response JSON against ``expected`` (default: expect ⊆ actual).

        Defaults come from ``settings.assertx`` / session-bound assert config:
        ``mode="loose"``, ``allow_extra=True``.

        Exclude merge order: global ``assertx.exclude`` → ``meta["exclude"]`` →
        call-site ``exclude``.

        ``expected`` may contain matchers (``ANY`` / ``Regex`` / ``Approx``) or
        JSON markers (``{"$any": true}``, ``{"$regex": "..."}``,
        ``{"$approx": 1.0, "abs": 0.01}``).
        """
        cfg = self._resolve_cfg(settings)
        resolved_mode: CompareMode = mode if mode is not None else cfg.mode
        resolved_extra = cfg.allow_extra if allow_extra is None else allow_extra
        if resolved_mode not in ("loose", "strict"):
            raise ValueError(f"Unsupported compare mode: {resolved_mode!r}")

        meta_exclude: Sequence[str] | None = None
        if meta is not None:
            raw = meta.get("exclude")
            if raw is not None and not isinstance(raw, (list, tuple)):
                raise TypeError("meta['exclude'] must be a list of path/key strings")
            meta_exclude = raw
        excludes = merge_excludes(cfg.exclude, meta_exclude, exclude)

        root = path or "$"
        try:
            if path is not None:
                actual = self.response.extract(path, default=None)
                if actual is None:
                    raise AssertionErrorX(
                        self._plain_message(f"JSONPath not found: {path}", msg),
                        response=self.response,
                    )
            else:
                actual = self.response.json()
        except AssertionErrorX:
            raise
        except Exception as exc:
            raise AssertionErrorX(
                self._plain_message(f"Response is not JSON: {exc}", msg),
                response=self.response,
            ) from exc

        diffs = compare_values(
            actual,
            expected,
            mode=resolved_mode,
            exclude=excludes,
            allow_extra=resolved_extra,
            path=root,
        )
        if diffs:
            self._raise_diffs("Body assertion failed", diffs, msg=msg)
        return self


class _ValueCheck(_AssertCfgMixin):
    """Fluent assertions for DB rows, lists, and other non-response values."""

    def __init__(self, actual: Any, *, settings: Settings | AssertSettings | None = None) -> None:
        self.actual = actual
        self._response = None
        self._settings = settings

    def is_not_none(self, *, msg: str | None = None) -> _ValueCheck:
        if self.actual is None:
            raise AssertionErrorX(
                self._plain_message("Expected value to be not None, got None", msg)
            )
        return self

    def is_none(self, *, msg: str | None = None) -> _ValueCheck:
        if self.actual is not None:
            raise AssertionErrorX(
                self._plain_message(f"Expected value to be None, got {self.actual!r}", msg)
            )
        return self

    def count(self, n: int, *, msg: str | None = None) -> _ValueCheck:
        """Assert ``len(actual) == n`` (rows / list / other sized collection)."""
        size = self._sized_len(msg=msg)
        if size != n:
            raise AssertionErrorX(self._plain_message(f"Expected count {n}, got {size}", msg))
        return self

    def count_at_least(self, n: int, *, msg: str | None = None) -> _ValueCheck:
        size = self._sized_len(msg=msg)
        if size < n:
            raise AssertionErrorX(self._plain_message(f"Expected count >= {n}, got {size}", msg))
        return self

    def count_at_most(self, n: int, *, msg: str | None = None) -> _ValueCheck:
        size = self._sized_len(msg=msg)
        if size > n:
            raise AssertionErrorX(self._plain_message(f"Expected count <= {n}, got {size}", msg))
        return self

    def equals(
        self,
        expected: Any,
        *,
        mode: CompareMode | None = None,
        exclude: Sequence[str] | None = None,
        allow_extra: bool | None = None,
        settings: Settings | AssertSettings | None = None,
        msg: str | None = None,
    ) -> _ValueCheck:
        """Deep-compare ``actual`` to ``expected`` (same engine as ``body``).

        Default: ``loose`` + ``allow_extra`` so you only list fields/rows you care
        about. Pass ``allow_extra=False`` when the structure must match exactly.

        For a list of rows, prefer ``mode="loose"`` (default) so order does not
        matter; use ``count(n)`` when the row count must be exact.
        """
        resolved_mode, resolved_extra, excludes = self._resolve_compare_opts(
            mode=mode,
            exclude=exclude,
            allow_extra=allow_extra,
            settings=settings,
        )
        diffs = compare_values(
            self.actual,
            expected,
            mode=resolved_mode,
            exclude=excludes,
            allow_extra=resolved_extra,
            path="$",
        )
        if diffs:
            self._raise_diffs("Value assertion failed", diffs, msg=msg)
        return self

    def contains(
        self,
        expected: Any,
        *,
        mode: CompareMode | None = None,
        exclude: Sequence[str] | None = None,
        allow_extra: bool | None = None,
        settings: Settings | AssertSettings | None = None,
        msg: str | None = None,
    ) -> _ValueCheck:
        """Assert a sized collection contains at least one item matching ``expected``.

        Equivalent to ``equals([expected], allow_extra=True)`` under list compare
        rules (other items may exist). ``allow_extra`` here applies to **item**
        field comparison (default from assert settings), not to list length.
        """
        if not isinstance(self.actual, (list, tuple)):
            raise AssertionErrorX(
                self._plain_message(
                    f"contains() requires a list/tuple, got {type(self.actual).__name__}",
                    msg,
                )
            )
        resolved_mode, resolved_extra, excludes = self._resolve_compare_opts(
            mode=mode,
            exclude=exclude,
            allow_extra=allow_extra,
            settings=settings,
        )
        for index, item in enumerate(self.actual):
            diffs = compare_values(
                item,
                expected,
                mode=resolved_mode,
                exclude=excludes,
                allow_extra=resolved_extra,
                path=f"$[{index}]",
            )
            if not diffs:
                return self
        raise AssertionErrorX(
            self._plain_message(f"No item matching expected {expected!r}", msg)
        )

    def _sized_len(self, *, msg: str | None = None) -> int:
        if self.actual is None:
            raise AssertionErrorX(
                self._plain_message("Expected a sized collection, got None", msg)
            )
        if isinstance(self.actual, (str, bytes)):
            raise AssertionErrorX(
                self._plain_message(
                    f"count() is for collections (e.g. DB rows), got {type(self.actual).__name__}",
                    msg,
                )
            )
        if not isinstance(self.actual, Sized):
            raise AssertionErrorX(
                self._plain_message(
                    f"Expected a sized collection, got {type(self.actual).__name__}",
                    msg,
                )
            )
        return len(self.actual)


def check(
    subject: Response | Any,
    *,
    settings: Settings | AssertSettings | None = None,
) -> _Check | _ValueCheck:
    """Fluent assertion entry.

    - ``check(resp).status(200).body(expect, meta=meta_data)`` — HTTP response
    - ``check(row).equals({...})`` / ``check(rows).count(2).equals([...])`` — DB / values
    """
    if isinstance(subject, Response):
        return _Check(subject, settings=settings)
    return _ValueCheck(subject, settings=settings)
