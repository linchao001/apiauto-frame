"""Deep JSON body comparison for full-payload assertions."""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Literal, Sequence

from zframe.assertx.matchers import Matcher, coerce_expected

CompareMode = Literal["loose", "strict"]

_BARE_KEY_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def merge_excludes(*groups: Sequence[str] | None) -> list[str]:
    """Union exclude specs preserving first-seen order."""
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        if not group:
            continue
        for raw in group:
            spec = str(raw).strip()
            if not spec or spec in seen:
                continue
            seen.add(spec)
            merged.append(spec)
    return merged


def compare_values(
    actual: Any,
    expected: Any,
    *,
    mode: CompareMode = "loose",
    exclude: Sequence[str] | None = None,
    allow_extra: bool = True,
    path: str = "$",
) -> list[str]:
    """Return human-readable diffs; empty list means equal under the given rules.

    - ``loose``: list order is ignored (bag match); dict key order never matters.
    - ``strict``: lists compare by index.
    - ``exclude``: dotted/JSONPath-like paths (``data.ts``, ``$.data.ts``,
      ``items[*].id``) or bare key names stripped at any depth (``requestId``).
    - ``allow_extra``: if True (default), actual may contain keys/items beyond
      expected (expect ⊆ actual); if False, structures must match fully.
    """
    left = apply_excludes(copy.deepcopy(actual), exclude)
    right = coerce_expected(apply_excludes(copy.deepcopy(expected), exclude))
    return _diff(left, right, mode=mode, allow_extra=allow_extra, path=path)


def apply_excludes(data: Any, exclude: Sequence[str] | None) -> Any:
    if not exclude:
        return data
    for raw in exclude:
        spec = str(raw).strip()
        if not spec:
            continue
        if _is_bare_key(spec):
            _strip_key_anywhere(data, spec)
        else:
            _delete_by_path(data, _parse_path(spec))
    return data


def _is_bare_key(spec: str) -> bool:
    if not spec or spec[0].isdigit():
        return False
    return all(ch in _BARE_KEY_CHARS for ch in spec) and ("." not in spec) and ("[" not in spec)


def _parse_path(spec: str) -> list[str | int | None]:
    import re

    token_re = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)|\[(\*|\d+)\]")
    text = spec.strip()
    if text.startswith("$"):
        text = text[1:]
    if text.startswith("."):
        text = text[1:]
    if not text:
        return []
    tokens: list[str | int | None] = []
    pos = 0
    while pos < len(text):
        if text[pos] == ".":
            pos += 1
            continue
        match = token_re.match(text, pos)
        if not match:
            raise ValueError(f"Invalid exclude path: {spec!r}")
        key, index = match.groups()
        if key is not None:
            tokens.append(key)
        elif index == "*":
            tokens.append(None)
        else:
            tokens.append(int(index))
        pos = match.end()
    return tokens


def _strip_key_anywhere(data: Any, key: str) -> None:
    if isinstance(data, dict):
        data.pop(key, None)
        for value in data.values():
            _strip_key_anywhere(value, key)
    elif isinstance(data, list):
        for item in data:
            _strip_key_anywhere(item, key)


def _delete_by_path(data: Any, tokens: list[str | int | None]) -> None:
    if not tokens:
        return
    head, *rest = tokens
    if head is None:  # [*]
        if not isinstance(data, list):
            return
        if not rest:
            data.clear()
            return
        for item in data:
            _delete_by_path(item, rest)
        return
    if isinstance(head, int):
        if not isinstance(data, list) or head >= len(data):
            return
        if not rest:
            data.pop(head)
        else:
            _delete_by_path(data[head], rest)
        return
    if not isinstance(data, dict) or head not in data:
        return
    if not rest:
        del data[head]
    else:
        _delete_by_path(data[head], rest)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_plain_hashable(value: Any) -> bool:
    if isinstance(value, Matcher):
        return False
    if isinstance(value, (dict, list)):
        return False
    try:
        hash(value)
    except TypeError:
        return False
    return True


def _diff(
    actual: Any,
    expected: Any,
    *,
    mode: CompareMode,
    allow_extra: bool,
    path: str,
) -> list[str]:
    if isinstance(expected, Matcher):
        if expected.matches(actual):
            return []
        return [f"{path}: expected {expected.describe()}, got {actual!r}"]

    if isinstance(expected, dict):
        return _diff_dict(actual, expected, mode=mode, allow_extra=allow_extra, path=path)
    if isinstance(expected, list):
        return _diff_list(actual, expected, mode=mode, allow_extra=allow_extra, path=path)

    if isinstance(expected, bool) or isinstance(actual, bool):
        if actual is not expected:
            return [f"{path}: expected {expected!r}, got {actual!r}"]
        return []

    if _is_number(expected) and _is_number(actual):
        if actual != expected:
            return [f"{path}: expected {expected!r}, got {actual!r}"]
        return []

    if type(actual) is not type(expected):
        return [
            f"{path}: type mismatch: expected {type(expected).__name__}, "
            f"got {type(actual).__name__}"
        ]
    if actual != expected:
        return [f"{path}: expected {expected!r}, got {actual!r}"]
    return []


def _diff_dict(
    actual: Any,
    expected: dict[str, Any],
    *,
    mode: CompareMode,
    allow_extra: bool,
    path: str,
) -> list[str]:
    if not isinstance(actual, dict):
        return [f"{path}: expected object, got {type(actual).__name__}"]
    errors: list[str] = []
    for key, exp_val in expected.items():
        child = f"{path}.{key}"
        if key not in actual:
            errors.append(f"{child}: missing in actual")
            continue
        errors.extend(
            _diff(actual[key], exp_val, mode=mode, allow_extra=allow_extra, path=child)
        )
    if not allow_extra:
        extra = sorted(set(actual) - set(expected))
        if extra:
            errors.append(f"{path}: unexpected keys in actual: {extra}")
    return errors


def _diff_list(
    actual: Any,
    expected: list[Any],
    *,
    mode: CompareMode,
    allow_extra: bool,
    path: str,
) -> list[str]:
    if not isinstance(actual, list):
        return [f"{path}: expected array, got {type(actual).__name__}"]

    if mode == "strict":
        errors: list[str] = []
        if not allow_extra and len(actual) != len(expected):
            errors.append(
                f"{path}: list length mismatch: expected {len(expected)}, got {len(actual)}"
            )
        elif allow_extra and len(actual) < len(expected):
            errors.append(
                f"{path}: list too short: expected at least {len(expected)}, got {len(actual)}"
            )
        limit = min(len(actual), len(expected))
        for index in range(limit):
            errors.extend(
                _diff(
                    actual[index],
                    expected[index],
                    mode=mode,
                    allow_extra=allow_extra,
                    path=f"{path}[{index}]",
                )
            )
        return errors

    # loose + all plain hashables → Counter multiset (O(n))
    if expected and all(_is_plain_hashable(x) for x in expected) and all(
        _is_plain_hashable(x) for x in actual
    ):
        return _diff_list_multiset(actual, expected, allow_extra=allow_extra, path=path)

    # loose: order-insensitive bag match (O(n²) for nested structures)
    errors = []
    unused = list(range(len(actual)))
    for index, exp_item in enumerate(expected):
        match_at: int | None = None
        for candidate in unused:
            nested = _diff(
                actual[candidate],
                exp_item,
                mode=mode,
                allow_extra=allow_extra,
                path=f"{path}[{index}]",
            )
            if not nested:
                match_at = candidate
                break
        if match_at is None:
            errors.append(f"{path}[{index}]: no matching item for expected {exp_item!r}")
        else:
            unused.remove(match_at)
    if not allow_extra and unused:
        leftovers = [actual[i] for i in unused]
        errors.append(f"{path}: unexpected extra items in actual: {leftovers!r}")
    return errors


def _diff_list_multiset(
    actual: list[Any],
    expected: list[Any],
    *,
    allow_extra: bool,
    path: str,
) -> list[str]:
    act_counts = Counter(actual)
    exp_counts = Counter(expected)
    errors: list[str] = []
    for item, need in exp_counts.items():
        have = act_counts[item]
        if have < need:
            errors.append(
                f"{path}: missing item {item!r}: expected {need}, got {have}"
            )
    if not allow_extra:
        for item, have in act_counts.items():
            need = exp_counts[item]
            if have > need:
                errors.append(
                    f"{path}: unexpected extra item {item!r}: expected {need}, got {have}"
                )
    return errors
