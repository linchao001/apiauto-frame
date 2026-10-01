"""Strengthened assertx coverage: sample payload, fuzz, concurrency."""

from __future__ import annotations

import copy
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import pytest

from zframe import ANY, Approx, Regex, SoftAssertions, check
from zframe.assertx.checkers import AssertionErrorX
from zframe.assertx.compare import apply_excludes, compare_values, merge_excludes
from zframe.assertx.defaults import (
    bind_assert_settings,
    get_assert_settings,
    reset_assert_settings,
)
from zframe.client.response import Response
from zframe.config.models import AssertSettings

def _resp(payload: object, *, status: int = 200) -> Response:
    return Response(httpx.Response(status, json=payload), elapsed_ms=0.0)


def _sample_case() -> tuple[dict, dict]:
    """Neutral fixture shaped like typical API expect + meta.exclude."""
    meta_data = {
        "id": "S01",
        "title": "sample profile",
        "exclude": ["requestId", "timestamp"],
    }
    expect = {
        "code": 0,
        "message": "ok",
        "data": {
            "code": "item-1",
            "itemId": "1",
            "name": "Sample",
        },
    }
    return meta_data, expect


# ---------------------------------------------------------------------------
# Sample profile body asserts (meta.exclude + allow_extra)
# ---------------------------------------------------------------------------


def test_sample_profile_body_with_volatile_fields():
    """meta.exclude + extra actual fields under allow_extra."""
    meta_data, expect = _sample_case()
    actual = {
        **expect,
        "requestId": "rid-live-001",
        "timestamp": 1_720_000_000_000,
        "data": {
            **expect["data"],
            "avatar": "https://cdn.example/item.png",  # allow_extra
        },
    }
    check(_resp(actual)).status(200).body(expect, meta=meta_data)


def test_sample_profile_fails_when_payload_field_wrong():
    meta_data, expect = _sample_case()
    actual = {
        **expect,
        "requestId": "rid",
        "timestamp": 9,
        "data": {**expect["data"], "code": "other"},
    }
    with pytest.raises(AssertionErrorX, match="Body assertion failed"):
        check(_resp(actual)).body(expect, meta=meta_data)


def test_sample_profile_global_and_meta_and_callsite_exclude_merge():
    meta_data, expect = _sample_case()
    actual = {
        **expect,
        "requestId": "r",
        "timestamp": 1,
        "traceId": "tr",
        "nonce": "n1",
        "data": dict(expect["data"]),
    }
    token = bind_assert_settings(AssertSettings(exclude=["traceId"]))
    try:
        check(_resp(actual)).body(
            expect,
            meta=meta_data,
            exclude=["nonce"],
        )
        # without callsite exclude, nonce should surface when allow_extra=False
        with pytest.raises(AssertionErrorX):
            check(_resp(actual)).body(
                expect,
                meta=meta_data,
                allow_extra=False,
            )
    finally:
        reset_assert_settings(token)


def test_sample_profile_json_markers_and_any_for_dynamic_ids():
    meta_data, expect = _sample_case()
    expect_dyn = copy.deepcopy(expect)
    expect_dyn["data"]["itemId"] = {"$any": True}
    expect_dyn["message"] = {"$regex": "^ok"}
    actual = {
        **expect,
        "requestId": "x",
        "timestamp": 2,
        "data": {**expect["data"], "itemId": "999"},
    }
    check(_resp(actual)).body(expect_dyn, meta=meta_data)


# ---------------------------------------------------------------------------
# SoftAssertions + check() integration
# ---------------------------------------------------------------------------


def test_soft_collects_multiple_check_body_failures():
    soft = SoftAssertions()
    ok = _resp({"code": 0})
    bad = _resp({"code": 1, "msg": "no"})
    soft.run(lambda: check(ok).body({"code": 0}))
    soft.run(lambda: check(bad).status(200).body({"code": 0}))
    soft.run(lambda: check(bad).jsonpath("$.msg", "yes"))
    soft.check(False, "manual")
    with pytest.raises(AssertionErrorX, match="Soft assertion \\(3 differences\\)"):
        soft.assert_all()


# ---------------------------------------------------------------------------
# Randomized / property-style robustness
# ---------------------------------------------------------------------------


def _rand_scalar(rng: random.Random) -> object:
    choice = rng.randint(0, 5)
    if choice == 0:
        return rng.randint(-50, 50)
    if choice == 1:
        return rng.random() * 10
    if choice == 2:
        return rng.choice([True, False])
    if choice == 3:
        return None
    if choice == 4:
        return rng.choice(["a", "b", "admin", "系统管理员", ""])
    return rng.choice(["x", "y"])


def _rand_json(rng: random.Random, depth: int = 0) -> object:
    if depth >= 3:
        return _rand_scalar(rng)
    kind = rng.randint(0, 2)
    if kind == 0:
        return _rand_scalar(rng)
    if kind == 1:
        n = rng.randint(0, 4)
        return [_rand_json(rng, depth + 1) for _ in range(n)]
    keys = [f"k{i}" for i in range(rng.randint(0, 4))]
    # occasionally inject volatile keys used in sample payloads
    if rng.random() < 0.4:
        keys.extend(["requestId", "timestamp"])
    rng.shuffle(keys)
    return {k: _rand_json(rng, depth + 1) for k in keys}


def test_compare_reflexive_and_exclude_idempotent_random():
    rng = random.Random(20260805)
    for _ in range(40):
        payload = _rand_json(rng)
        assert compare_values(payload, copy.deepcopy(payload)) == []
        assert compare_values(payload, copy.deepcopy(payload), mode="strict") == []

        excluded = apply_excludes(copy.deepcopy(payload), ["requestId", "timestamp"])
        again = apply_excludes(copy.deepcopy(excluded), ["requestId", "timestamp"])
        assert excluded == again
        assert compare_values(payload, payload, exclude=["requestId", "timestamp"]) == []


def test_loose_subset_with_extra_noise_random():
    rng = random.Random(42)
    for _ in range(30):
        expected = _rand_json(rng)
        if not isinstance(expected, dict):
            expected = {"root": expected}
        actual = copy.deepcopy(expected)
        actual["requestId"] = f"rid-{rng.randint(1, 9999)}"
        actual["timestamp"] = rng.randint(1, 10**9)
        actual["noise"] = _rand_json(rng)
        assert (
            compare_values(
                actual,
                expected,
                exclude=["requestId", "timestamp"],
                allow_extra=True,
            )
            == []
        )


def test_allow_extra_false_detects_injected_key_random():
    rng = random.Random(7)
    for _ in range(20):
        expected = {"code": 0, "data": {"v": rng.randint(0, 9)}}
        actual = copy.deepcopy(expected)
        actual["leak"] = "x"
        diffs = compare_values(actual, expected, allow_extra=False)
        assert any("unexpected keys" in d for d in diffs)


def test_merge_excludes_associative_random():
    rng = random.Random(99)
    for _ in range(25):
        groups = []
        for _g in range(rng.randint(0, 4)):
            group = [rng.choice(["a", "b", "c", "requestId", "data.ts", ""]) for _ in range(rng.randint(0, 5))]
            groups.append(group if rng.random() > 0.2 else None)
        one = merge_excludes(*groups)
        # re-merge in chunks should preserve first-seen order of unique specs
        mid = len(groups) // 2
        two = merge_excludes(merge_excludes(*groups[:mid]), merge_excludes(*groups[mid:]))
        assert one == two


# ---------------------------------------------------------------------------
# Deep structure / wildcard stress
# ---------------------------------------------------------------------------


def test_deep_wildcard_exclude_and_index_paths():
    actual = {
        "rows": [
            {"id": 1, "meta": {"ts": 10, "ok": True}},
            {"id": 2, "meta": {"ts": 20, "ok": False}},
        ],
        "flags": ["a", "b", "c"],
    }
    expected = {
        "rows": [
            {"id": 1, "meta": {"ok": True}},
            {"id": 2, "meta": {"ok": False}},
        ],
        "flags": ["a", "c"],
    }
    assert (
        compare_values(
            actual,
            expected,
            exclude=["rows[*].meta.ts", "flags[1]"],
        )
        == []
    )


def test_nested_list_bag_with_matchers():
    actual = {
        "users": [
            {"name": "bob", "score": 1.002},
            {"name": "alice", "score": 2.0, "extra": 1},
        ]
    }
    expected = {
        "users": [
            {"name": "alice", "score": Approx(2.0, abs=0.01)},
            {"name": Regex(r"^bo"), "score": {"$approx": 1.0, "abs": 0.01}},
        ]
    }
    assert compare_values(actual, expected, mode="loose") == []
    assert compare_values(actual, expected, mode="strict")  # order differs → fail


def test_any_still_requires_key_presence():
    diffs = compare_values({"a": 1}, {"a": 1, "b": ANY})
    assert any("missing" in d for d in diffs)


# ---------------------------------------------------------------------------
# ContextVar concurrency isolation
# ---------------------------------------------------------------------------


def test_assert_settings_contextvar_isolated_across_threads():
    barrier = threading.Barrier(4)
    results: dict[str, str] = {}
    errors: list[BaseException] = []

    def worker(name: str, mode: str) -> None:
        try:
            token = bind_assert_settings(AssertSettings(mode=mode, exclude=[name]))
            try:
                barrier.wait(timeout=5)
                # other threads mutate their own context; ours must stay stable
                for _ in range(20):
                    cfg = get_assert_settings()
                    assert cfg.mode == mode
                    assert cfg.exclude == [name]
                results[name] = get_assert_settings().mode
            finally:
                reset_assert_settings(token)
        except BaseException as exc:  # noqa: BLE001 — collect for main thread
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("t0", "loose")),
        threading.Thread(target=worker, args=("t1", "strict")),
        threading.Thread(target=worker, args=("t2", "loose")),
        threading.Thread(target=worker, args=("t3", "strict")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors
    assert results == {"t0": "loose", "t1": "strict", "t2": "loose", "t3": "strict"}
    # main thread unbound → defaults
    assert get_assert_settings().mode == "loose"
    assert get_assert_settings().exclude == []


def test_check_body_uses_thread_local_defaults_under_pool():
    payloads = [
        ({"code": 0, "traceId": "a"}, "loose"),
        ({"code": 0, "traceId": "b"}, "strict"),
    ]

    def run_case(item: tuple[dict, str]) -> None:
        body, mode = item
        token = bind_assert_settings(AssertSettings(mode=mode, exclude=["traceId"]))
        try:
            check(_resp(body)).body({"code": 0})
            assert get_assert_settings().mode == mode
        finally:
            reset_assert_settings(token)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(run_case, payloads[i % 2]) for i in range(16)]
        for fut in as_completed(futures):
            fut.result()
