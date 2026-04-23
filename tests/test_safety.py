"""Tests for the safety mechanisms: OAuth URL masking and --full toggle."""

from chat2html import cli
from chat2html.cli import _is_oauth_url, _mask_oauth_urls, _render_tool_use_block

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


def test_safe_mode_omits_tool_result():
    cli._FULL = False
    tool_use = {
        "name": "Bash",
        "input": {"command": "rm -rf /important/path"},
        "id": "t1",
    }
    tool_result = {"content": [{"type": "text", "text": "secret data"}]}
    html = _render_tool_use_block(tool_use, tool_result)
    # Result is omitted entirely.
    assert "secret data" not in html
    # The bare command is also omitted ("command" is not in SAFE_TOOL_USE_FIELDS).
    assert "rm -rf" not in html
    assert "/important/path" not in html
    # The omission badge is rendered instead.
    assert "omitted" in html


def test_safe_mode_keeps_description_field():
    cli._FULL = False
    tool_use = {
        "name": "Bash",
        "input": {"command": "rm -rf x", "description": "tidy up"},
        "id": "t1",
    }
    html = _render_tool_use_block(tool_use, None)
    assert "tidy up" in html
    assert "rm -rf x" not in html


def test_full_mode_shows_tool_input_and_result():
    cli._FULL = True
    try:
        tool_use = {"name": "Bash", "input": {"command": "ls"}, "id": "t1"}
        tool_result = {"content": [{"type": "text", "text": "file_a.py"}]}
        html = _render_tool_use_block(tool_use, tool_result)
        assert "ls" in html
        assert "file_a.py" in html
    finally:
        cli._FULL = False
