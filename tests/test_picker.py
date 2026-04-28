"""Tests for the directory walker + per-format peek used by the TUI picker."""

import os

import pytest

from chat2html.format_detect import (
    FORMAT_CC_JSONL,
    FORMAT_CODEX_JSONL,
    FORMAT_MD,
)
from chat2html.picker import (
    _one_line,
    _peek_cc_jsonl,
    _peek_codex_jsonl,
    _peek_md,
    cap_items,
    walk_chat_files,
)


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Keep the preview cache out of the user's home during tests."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


def test_one_line_collapses_whitespace_and_truncates():
    assert _one_line("hello\n\n  world") == "hello world"
    long = "a" * 200
    assert _one_line(long, max_len=10) == "aaaaaaaaa…"


def test_peek_cc_jsonl(cc_text):
    assert _peek_cc_jsonl(cc_text).startswith("List the python files")


def test_peek_codex_jsonl_skips_env_context(codex_text):
    # The very first user message in the Codex sample is an
    # <environment_context> harness block; peek must skip it and return
    # the actual prompt that follows.
    assert _peek_codex_jsonl(codex_text).startswith("Refactor parse_users")


def test_peek_md(markdown_text):
    assert _peek_md(markdown_text).startswith("How do I reverse a list")


def test_walk_chat_files_filters_and_sorts(
    tmp_path, cc_text, codex_text, markdown_text
):
    cc = tmp_path / "session.jsonl"
    cc.write_text(cc_text, encoding="utf-8")
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    codex = codex_dir / "rollout.jsonl"
    codex.write_text(codex_text, encoding="utf-8")
    md = tmp_path / "notes.md"
    md.write_text(markdown_text, encoding="utf-8")

    # Noise that should be ignored:
    (tmp_path / "README.md").write_text("# Just a readme\n", encoding="utf-8")
    (tmp_path / "out.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "empty.jsonl").write_text("", encoding="utf-8")
    hidden = tmp_path / ".git"
    hidden.mkdir()
    (hidden / "should_skip.jsonl").write_text(cc_text, encoding="utf-8")

    # Stagger mtimes so ordering is deterministic: codex newest, then md, then cc.
    os.utime(cc, (1_700_000_000, 1_700_000_000))
    os.utime(md, (1_700_000_100, 1_700_000_100))
    os.utime(codex, (1_700_000_200, 1_700_000_200))

    items = walk_chat_files(tmp_path)

    paths = [str(i.path.relative_to(tmp_path)) for i in items]
    # README.md and out.html are gone; .git/ is gone; empty file is gone;
    # ordering is mtime desc.
    assert paths == ["codex/rollout.jsonl", "notes.md", "session.jsonl"]

    fmts = {i.path.name: i.fmt for i in items}
    assert fmts["session.jsonl"] == FORMAT_CC_JSONL
    assert fmts["rollout.jsonl"] == FORMAT_CODEX_JSONL
    assert fmts["notes.md"] == FORMAT_MD

    previews = {i.path.name: i.preview for i in items}
    assert previews["session.jsonl"].startswith("List the python files")
    assert previews["rollout.jsonl"].startswith("Refactor parse_users")
    assert previews["notes.md"].startswith("How do I reverse a list")


def test_peek_cc_jsonl_skips_bare_slash_commands():
    # Bare /clear (no args) is housekeeping — preview should be the
    # real user prompt that follows.
    jsonl = "\n".join(
        [
            (
                '{"type":"user","uuid":"u-001","sessionId":"s","timestamp":"t",'
                '"message":{"role":"user","content":'
                '"<command-name>/clear</command-name><command-args></command-args>"'
                "}}"
            ),
            (
                '{"type":"user","uuid":"u-002","sessionId":"s","timestamp":"t",'
                '"message":{"role":"user","content":"actually fix the parser"}}'
            ),
        ]
    )
    assert _peek_cc_jsonl(jsonl) == "actually fix the parser"


def test_peek_cc_jsonl_keeps_slash_commands_with_args():
    # Slash commands carrying real intent (skill invocation with a
    # prompt) should survive as the preview.
    jsonl = (
        '{"type":"user","uuid":"u-001","sessionId":"s","timestamp":"t",'
        '"message":{"role":"user","content":'
        '"<command-name>/example-skill</command-name>'
        '<command-args>do the thing</command-args>"'
        "}}"
    )
    assert _peek_cc_jsonl(jsonl) == "/example-skill do the thing"


def test_walk_chat_files_respects_max_depth(tmp_path, cc_text):
    # root/a/b/c/deep.jsonl is 3 levels under root.
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "deep.jsonl").write_text(cc_text, encoding="utf-8")
    (tmp_path / "shallow.jsonl").write_text(cc_text, encoding="utf-8")

    # max_depth=0 → root files only.
    items = walk_chat_files(tmp_path, max_depth=0)
    assert [i.path.name for i in items] == ["shallow.jsonl"]

    # max_depth=2 → root + 2 levels, still misses deep.jsonl (depth 3).
    items = walk_chat_files(tmp_path, max_depth=2)
    assert [i.path.name for i in items] == ["shallow.jsonl"]

    # max_depth=3 → catches deep.jsonl too.
    items = walk_chat_files(tmp_path, max_depth=3)
    assert sorted(i.path.name for i in items) == ["deep.jsonl", "shallow.jsonl"]


def test_cap_items():
    from pathlib import Path

    from chat2html.picker import ChatFile

    items = [
        ChatFile(path=Path(f"f{i}"), fmt="md", mtime=i, preview="")
        for i in range(5)
    ]
    capped, dropped = cap_items(items, max_files=3)
    assert len(capped) == 3 and dropped == 2
    capped, dropped = cap_items(items, max_files=10)
    assert capped == items and dropped == 0
    capped, dropped = cap_items(items, max_files=0)  # 0 disables cap
    assert capped == items and dropped == 0


def test_walk_chat_files_caches_by_mtime(tmp_path, cc_text, monkeypatch):
    """Second walk reuses cached fmt/preview when mtime hasn't changed."""
    f = tmp_path / "session.jsonl"
    f.write_text(cc_text, encoding="utf-8")
    os.utime(f, (1_700_000_000, 1_700_000_000))

    walk_chat_files(tmp_path)  # populate cache

    # Make the file unreadable-ish by replacing the head with garbage; the
    # cached entry should still win because mtime didn't change.
    from chat2html import picker

    sentinel = "CACHED_PREVIEW_VALUE"
    monkeypatch.setattr(
        picker, "_read_head", lambda *a, **kw: pytest.fail("cache should be hit")
    )
    # Inject a sentinel preview into the cache so we can confirm it's used.
    cache = picker._load_cache()
    key = str(f.resolve())
    cache[key]["preview"] = sentinel
    picker._save_cache(cache)

    items = walk_chat_files(tmp_path)
    assert len(items) == 1
    assert items[0].preview == sentinel
