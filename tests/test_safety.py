"""Tests for the safety mechanisms: OAuth URL masking and --full toggle."""

from chat2html import render
from chat2html.ir import ToolUseBlock
from chat2html.render import _render_tool_use_block
from chat2html.safety import _is_oauth_url, _mask_oauth_urls

# ─── OAuth URL detection ───────────────────────────────────


def test_is_oauth_url_detects_state_param():
    assert _is_oauth_url("https://example.com/cb?state=abc&code=xyz")


def test_is_oauth_url_detects_oauth_path():
    assert _is_oauth_url("https://example.com/oauth/authorize")


def test_is_oauth_url_detects_known_provider():
    assert _is_oauth_url("https://accounts.google.com/o/oauth2/auth")


def test_is_oauth_url_ignores_plain_url():
    assert not _is_oauth_url("https://example.com/docs/getting-started")


# ─── Masking ───────────────────────────────────────────────


def test_mask_replaces_oauth_url():
    text = "Open https://accounts.google.com/o/oauth2/auth?state=x to log in."
    out = _mask_oauth_urls(text)
    assert "[redacted OAuth URL]" in out
    assert "accounts.google.com" not in out


def test_mask_preserves_trailing_punctuation():
    text = "See https://example.com/oauth/cb?state=x."
    out = _mask_oauth_urls(text)
    assert out.endswith(".")
    assert "[redacted OAuth URL]" in out


def test_mask_leaves_plain_url_alone():
    text = "Docs at https://example.com/docs"
    assert _mask_oauth_urls(text) == text


# ─── Safe vs --full tool rendering ─────────────────────────


def test_safe_mode_omits_tool_result(monkeypatch):
    monkeypatch.setattr(render, "_FULL", False)
    block = ToolUseBlock(
        name="Bash",
        input={"command": "rm -rf /important/path"},
        result="secret data",
    )
    html = _render_tool_use_block(block)
    # Result is omitted entirely.
    assert "secret data" not in html
    # The bare command is also omitted ("command" is not in SAFE_TOOL_USE_FIELDS).
    assert "rm -rf" not in html
    assert "/important/path" not in html
    # The omission badge is rendered instead.
    assert "omitted" in html


def test_safe_mode_keeps_description_field(monkeypatch):
    monkeypatch.setattr(render, "_FULL", False)
    block = ToolUseBlock(
        name="Bash",
        input={"command": "rm -rf x", "description": "tidy up"},
        result=None,
    )
    html = _render_tool_use_block(block)
    assert "tidy up" in html
    assert "rm -rf x" not in html


def test_title_masks_oauth_url():
    """The conversation title is built from the first user prompt; an OAuth
    URL there must not leak into <title>, <h1>, or any derived filename."""
    import json

    from chat2html.parsers import parse_codex_jsonl

    text = "\n".join(
        [
            json.dumps(
                {
                    "timestamp": "2026-01-15T10:00:00.000Z",
                    "type": "session_meta",
                    "payload": {"id": "x", "cwd": "/tmp"},
                }
            ),
            json.dumps(
                {
                    "timestamp": "2026-01-15T10:00:01.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Check https://accounts.google.com/o/oauth2/auth"
                                    "?state=secret&code=leak — does this URL parse?"
                                ),
                            }
                        ],
                    },
                }
            ),
        ]
    )
    title, _, _ = parse_codex_jsonl(text)
    assert "accounts.google.com" not in title
    assert "secret" not in title
    assert "[redacted OAuth URL]" in title


def test_full_mode_shows_tool_input_and_result(monkeypatch):
    monkeypatch.setattr(render, "_FULL", True)
    block = ToolUseBlock(
        name="Bash",
        input={"command": "ls"},
        result="file_a.py",
    )
    html = _render_tool_use_block(block)
    assert "ls" in html
    assert "file_a.py" in html
