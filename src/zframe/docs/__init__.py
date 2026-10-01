"""Bundled framework documentation (``zframe/docs/to_agent``; optional ``to_user``)."""

from __future__ import annotations

from pathlib import Path

_DOC_SUFFIX = ".md"
_USER_DIR = "to_user"
_AGENT_DIR = "to_agent"
_AUDIENCE_ALIASES = {
    "user": _USER_DIR,
    "to_user": _USER_DIR,
    "agent": _AGENT_DIR,
    "to_agent": _AGENT_DIR,
}


class DocsError(Exception):
    """Missing docs directory or unknown topic."""


def resolve_docs_dir() -> Path:
    """Locate the bundled docs root (wheel install or repo checkout)."""
    return _resolve_docs_root()


def _resolve_docs_root() -> Path:
    here = Path(__file__).resolve().parent
    if (here / _USER_DIR).is_dir() or (here / _AGENT_DIR).is_dir():
        return here

    repo_docs = here.parents[2] / "docs"
    if (repo_docs / _USER_DIR).is_dir() or (repo_docs / _AGENT_DIR).is_dir():
        return repo_docs

    raise DocsError(
        f"Documentation not found (looked under {here} and {repo_docs})"
    )


def _normalize_audience(raw: str) -> str:
    key = raw.strip().lower()
    if key not in _AUDIENCE_ALIASES:
        raise DocsError(
            f"Unknown audience {raw!r}; use user/to_user or agent/to_agent"
        )
    return _AUDIENCE_ALIASES[key]


def _topic_path(root: Path, audience: str, stem: str) -> Path:
    if audience == _AGENT_DIR and stem in ("", "index"):
        return root / _AGENT_DIR / "index.md"
    return root / audience / f"{stem}{_DOC_SUFFIX}"


def list_topics() -> list[str]:
    """Return sorted topic ids (``agent/http``, bare stems, optional ``user/...``)."""
    root = _resolve_docs_root()
    topics: set[str] = set()

    agent_dir = root / _AGENT_DIR
    if agent_dir.is_dir():
        topics.add("agent")
        for path in agent_dir.glob(f"*{_DOC_SUFFIX}"):
            if path.stem != "index":
                topics.add(f"agent/{path.stem}")
                topics.add(path.stem)

    user_dir = root / _USER_DIR
    if user_dir.is_dir():
        for path in user_dir.glob(f"*{_DOC_SUFFIX}"):
            topics.add(path.stem)
            topics.add(f"user/{path.stem}")

    return sorted(topics)


def resolve_topic(name: str) -> Path:
    """Resolve a topic id to a doc file path.

    Bare stems prefer ``to_user`` when present, otherwise ``to_agent``.
    """
    raw = (name or "").strip()
    if not raw:
        raise DocsError("Topic name is required")

    stem = raw.removesuffix(_DOC_SUFFIX)
    root = _resolve_docs_root()

    if stem == "agent":
        path = _topic_path(root, _AGENT_DIR, "index")
        if path.is_file():
            return path

    if "/" in stem:
        audience_raw, topic_stem = stem.split("/", 1)
        audience = _normalize_audience(audience_raw)
        path = _topic_path(root, audience, topic_stem)
        if path.is_file():
            return path
    else:
        user_path = _topic_path(root, _USER_DIR, stem)
        if user_path.is_file():
            return user_path
        agent_path = _topic_path(root, _AGENT_DIR, stem)
        if agent_path.is_file():
            return agent_path

    available = ", ".join(list_topics()) or "(none)"
    raise DocsError(f"Unknown topic {name!r}; available: {available}")
