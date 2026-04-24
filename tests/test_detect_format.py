from chat2html.format_detect import (
    FORMAT_CC_JSONL,
    FORMAT_CLAUDEAI,
    FORMAT_CODEX_JSONL,
    FORMAT_MD,
    detect_format,
)


def test_detect_codex(codex_text):
    assert detect_format("codex_sample.jsonl", codex_text) == FORMAT_CODEX_JSONL


def test_detect_claude_code(cc_text):
    assert detect_format("claude_code_sample.jsonl", cc_text) == FORMAT_CC_JSONL


def test_detect_claude_ai(claudeai_text):
    assert detect_format("claude_ai_sample.json", claudeai_text) == FORMAT_CLAUDEAI


def test_detect_markdown_by_extension(markdown_text):
    assert detect_format("markdown_sample.md", markdown_text) == FORMAT_MD


def test_detect_markdown_by_content():
    text = "## Human:\nhi\n\n## Claude:\nhello\n"
    assert detect_format("notes.txt", text) == FORMAT_MD


def test_detect_empty_falls_back_to_md():
    assert detect_format("anything.jsonl", "") == FORMAT_MD


def test_detect_codex_does_not_collide_with_cc(cc_text, codex_text):
    # Sanity: a Claude Code sample must not be classified as Codex even though
    # both have a top-level "type" field.
    assert detect_format("x.jsonl", cc_text) != FORMAT_CODEX_JSONL
    # And vice versa: Codex must not be classified as Claude Code.
    assert detect_format("x.jsonl", codex_text) != FORMAT_CC_JSONL
