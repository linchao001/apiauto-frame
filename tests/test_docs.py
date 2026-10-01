"""Bundled docs resolution and CLI --docs."""

from __future__ import annotations

from pathlib import Path

import pytest

from zframe.cli import main
from zframe.docs import DocsError, list_topics, resolve_docs_dir, resolve_topic


def test_resolve_docs_dir_from_repo():
    docs_dir = resolve_docs_dir()
    assert docs_dir.is_dir()
    assert (docs_dir / "to_agent" / "index.md").is_file()
    assert (docs_dir / "to_agent" / "http.md").is_file()


def test_list_topics_includes_agent_and_bare_stems():
    topics = list_topics()
    assert "agent" in topics
    assert "agent/http" in topics
    assert "http" in topics
    assert "config" in topics
    assert topics == sorted(topics)
    assert not any(t.startswith("user/") for t in topics)


def test_resolve_topic_bare_stem_to_agent():
    path = resolve_topic("http")
    assert path.name == "http.md"
    assert "to_agent" in path.parts
    assert path.is_file()


def test_resolve_topic_agent_module():
    path = resolve_topic("agent/http")
    assert path.name == "http.md"
    assert "to_agent" in path.parts


def test_resolve_topic_agent_index():
    path = resolve_topic("agent")
    assert path.name == "index.md"
    assert path.parent.name == "to_agent"


def test_resolve_topic_user_prefixed_missing():
    with pytest.raises(DocsError, match="Unknown topic"):
        resolve_topic("user/config.md")


def test_resolve_topic_unknown():
    with pytest.raises(DocsError, match="Unknown topic"):
        resolve_topic("not-a-real-topic")


def test_cli_docs_lists_topics(capsys: pytest.CaptureFixture[str]):
    assert main(["--docs"]) == 0
    out = capsys.readouterr().out
    assert "[zframe] docs:" in out
    assert "  agent" in out
    assert "  http" in out


def test_cli_docs_prints_agent_topic_path(capsys: pytest.CaptureFixture[str]):
    assert main(["--docs", "agent/parametrize"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("parametrize.md")
    assert "to_agent" in out.replace("\\", "/")
    assert Path(out).is_file()


def test_cli_docs_unknown_topic(capsys: pytest.CaptureFixture[str]):
    assert main(["--docs", "missing-topic"]) == 1
    err = capsys.readouterr().err
    assert "Unknown topic" in err


def test_cli_docs_open_requires_topic():
    with pytest.raises(SystemExit) as exc:
        main(["--docs", "--open"])
    assert exc.value.code == 2
