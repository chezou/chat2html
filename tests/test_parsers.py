"""Smoke tests for each parser.

Goal: lock in the high-level shape of each parser's output so the Phase 1
refactor can be verified by running these tests.
"""

import json

from chat2html.cli import (
    load_claudeai_export,
    parse_cc_jsonl,
    parse_claudeai_conversation,
    parse_codex_jsonl,
    parse_markdown,
)

# ─── Markdown ──────────────────────────────────────────────


def test_markdown_title_and_message_count(markdown_text):
    title, created, messages = parse_markdown(markdown_text)
    assert title == "Sample Conversation"
    # 2 user turns + 2 assistant turns
    assert len(messages) == 4
    assert messages[0]["role"] == "human"
    assert messages[1]["role"] == "assistant"


def test_markdown_first_message_body_includes_query(markdown_text):
    _, _, messages = parse_markdown(markdown_text)
    assert "reverse a list" in messages[0]["body_html"]


# ─── claude.ai export ──────────────────────────────────────


def test_claudeai_loads_two_conversations(claudeai_text):
    convs = load_claudeai_export(claudeai_text)
    assert len(convs) == 2
    assert convs[0]["name"] == "Reversing lists in Python"


def test_claudeai_parse_first_conversation(claudeai_text):
    convs = load_claudeai_export(claudeai_text)
    title, created, messages = parse_claudeai_conversation(convs[0])
    assert title == "Reversing lists in Python"
    assert created.startswith("2026-01-15")
    assert len(messages) == 2
    assert messages[0]["role"] == "human"
    assert messages[1]["role"] == "assistant"


# ─── Claude Code JSONL ─────────────────────────────────────


def test_cc_jsonl_basic_shape(cc_text):
    title, created, messages = parse_cc_jsonl(cc_text)
    assert "python files" in title.lower()
    assert created.startswith("2026-01-15")
    # 2 user turns (the second is a tool_result-only message which is dropped)
    # + 2 assistant bubbles. Tool-result-only user messages are skipped.
    assert len(messages) == 3
    assert messages[0]["role"] == "human"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "assistant"


def test_cc_jsonl_assistant_includes_tool_use(cc_text):
    _, _, messages = parse_cc_jsonl(cc_text)
    assistant_html = messages[1]["body_html"]
    # tool_use rendered as a <details class="tool-call"> block
    assert "tool-call" in assistant_html
    assert "Bash" in assistant_html


# ─── Codex JSONL ───────────────────────────────────────────


def test_codex_basic_shape(codex_text):
    title, created, messages = parse_codex_jsonl(codex_text)
    assert title == "Refactor parse_users in users.py to take a list of dicts."
    assert created.startswith("2026-01-15")
    # 2 user turns + 2 assistant bubbles (one per turn, with all assistant
    # text/reasoning/tool calls coalesced).
    assert len(messages) == 4
    assert messages[0]["role"] == "human"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "human"
    assert messages[3]["role"] == "assistant"


def test_codex_filters_developer_and_environment_context(codex_text):
    _, _, messages = parse_codex_jsonl(codex_text)
    bodies = "\n".join(m["body_html"] for m in messages)
    # System prompt under developer role must be filtered out.
    assert "permissions instructions" not in bodies
    # Auto-saved approval notice (also developer role) must be filtered.
    assert "Approved command prefix saved" not in bodies
    # environment_context user injection must be filtered.
    assert "<environment_context>" not in bodies


def test_codex_assistant_uses_codex_role_label(codex_text):
    _, _, messages = parse_codex_jsonl(codex_text)
    assistants = [m for m in messages if m["role"] == "assistant"]
    assert all(m.get("role_label") == "Codex" for m in assistants)


def test_codex_renders_function_call_with_paired_output(codex_text):
    _, _, messages = parse_codex_jsonl(codex_text)
    turn1_assistant = messages[1]["body_html"]
    # Two parallel exec_command calls + one pytest exec_command in turn 1.
    assert turn1_assistant.count("exec_command") >= 3
    # custom_tool_call (apply_patch) also rendered.
    assert "apply_patch" in turn1_assistant


def test_codex_renders_non_empty_reasoning_summary(codex_text):
    _, _, messages = parse_codex_jsonl(codex_text)
    turn1_assistant = messages[1]["body_html"]
    # The fixture has one non-empty reasoning summary in turn 1.
    assert "thinking" in turn1_assistant
    assert "the refactor is to define the new signature" in turn1_assistant


def test_codex_user_message_quoting_env_context_is_kept():
    """A user message that mentions <environment_context> but adds more
    content must NOT be filtered.

    Only the harness's bare env-context injection (whose entire body is just
    the tag) should be dropped.
    """
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
                                    "Why does my prompt include "
                                    "<environment_context>...</environment_context>? "
                                    "What does that block do?"
                                ),
                            }
                        ],
                    },
                }
            ),
            json.dumps(
                {
                    "timestamp": "2026-01-15T10:00:02.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "It's a harness injection.",
                            }
                        ],
                    },
                }
            ),
        ]
    )
    title, _, messages = parse_codex_jsonl(text)
    assert len(messages) == 2
    assert messages[0]["role"] == "human"
    assert "What does that block do?" in messages[0]["body_html"]
    # The title is derived from the first user prompt (truncated to 60 chars
    # if needed), so the kept message must drive it — not the default fallback.
    assert title.startswith("Why does my prompt include")


def test_codex_unmatched_function_call_still_renders():
    """A function_call without a matching function_call_output should still render."""
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
                        "content": [{"type": "input_text", "text": "do a thing"}],
                    },
                }
            ),
            json.dumps(
                {
                    "timestamp": "2026-01-15T10:00:02.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": '{"cmd":"ls"}',
                        "call_id": "call_orphan",
                    },
                }
            ),
        ]
    )
    _, _, messages = parse_codex_jsonl(text)
    # 1 user + 1 assistant bubble containing the orphan tool call
    assert len(messages) == 2
    assert "exec_command" in messages[1]["body_html"]
