"""Smoke tests for each parser.

Goal: lock in the high-level shape of each parser's output. Where useful,
assert directly on the IR (Block types) instead of rendered HTML; where
HTML rendering matters, render the message and check the resulting string.
"""

import json

from chat2html.ir import TextBlock, ThinkingBlock, ToolUseBlock
from chat2html.parsers import (
    load_claudeai_export,
    parse_cc_jsonl,
    parse_claudeai_conversation,
    parse_codex_jsonl,
    parse_markdown,
)
from chat2html.render import render_message


def _bodies(messages):
    return "\n".join(render_message(m) for m in messages)


# ─── Markdown ──────────────────────────────────────────────


def test_markdown_title_and_message_count(markdown_text):
    title, _created, messages = parse_markdown(markdown_text)
    assert title == "Sample Conversation"
    # 2 user turns + 2 assistant turns
    assert len(messages) == 4
    assert messages[0].role == "human"
    assert messages[1].role == "assistant"


def test_markdown_first_message_body_includes_query(markdown_text):
    _, _, messages = parse_markdown(markdown_text)
    assert "reverse a list" in render_message(messages[0])


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
    assert messages[0].role == "human"
    assert messages[1].role == "assistant"


# ─── Claude Code JSONL ─────────────────────────────────────


def test_cc_jsonl_basic_shape(cc_text):
    title, created, messages = parse_cc_jsonl(cc_text)
    assert "python files" in title.lower()
    assert created.startswith("2026-01-15")
    # 2 user turns (the second is a tool_result-only message which is dropped)
    # + 2 assistant bubbles. Tool-result-only user messages are skipped.
    assert len(messages) == 3
    assert [m.role for m in messages] == ["human", "assistant", "assistant"]


def test_cc_jsonl_assistant_block_types(cc_text):
    """The first assistant turn should be: thinking + text + tool_use."""
    _, _, messages = parse_cc_jsonl(cc_text)
    block_types = [type(b).__name__ for b in messages[1].blocks]
    assert block_types == ["ThinkingBlock", "TextBlock", "ToolUseBlock"]
    tool = messages[1].blocks[2]
    assert isinstance(tool, ToolUseBlock)
    assert tool.name == "Bash"
    # The tool result was paired in by the parser.
    assert tool.result is not None
    assert "users.py" in tool.result


def test_cc_jsonl_assistant_renders_tool_call(cc_text):
    _, _, messages = parse_cc_jsonl(cc_text)
    assistant_html = render_message(messages[1])
    assert "tool-call" in assistant_html
    assert "Bash" in assistant_html


def test_cc_jsonl_cleans_slash_command_wrappers():
    """Slash-command wrappers are extracted into a clean "/cmd args" string
    so the actual invocation stays visible in the conversation, instead of
    being dropped silently. Pure <local-command-stdout> noise (no
    <command-name> inside) is still filtered out.
    """
    text = "\n".join(
        [
            # Wrapper led by <command-message>, with non-empty args.
            json.dumps(
                {
                    "type": "user",
                    "uuid": "u-1",
                    "sessionId": "s-1",
                    "timestamp": "2026-01-15T10:00:00.000Z",
                    "message": {
                        "role": "user",
                        "content": (
                            "<command-message>codex:setup</command-message>\n"
                            "<command-name>/codex:setup</command-name>\n"
                            "<command-args>--enable-review-gate</command-args>"
                        ),
                    },
                }
            ),
            # Wrapper led by <local-command-caveat> wrapping a <command-name>.
            json.dumps(
                {
                    "type": "user",
                    "uuid": "u-2",
                    "sessionId": "s-1",
                    "timestamp": "2026-01-15T10:00:01.000Z",
                    "message": {
                        "role": "user",
                        "content": (
                            "<local-command-caveat>...</local-command-caveat>\n"
                            "<command-name>/plugin</command-name>\n"
                            "<command-args>install codex</command-args>\n"
                            "<local-command-stdout>ok</local-command-stdout>"
                        ),
                    },
                }
            ),
            # Pure stdout noise with no <command-name> — must still be dropped.
            json.dumps(
                {
                    "type": "user",
                    "uuid": "u-3",
                    "sessionId": "s-1",
                    "timestamp": "2026-01-15T10:00:02.000Z",
                    "message": {
                        "role": "user",
                        "content": (
                            "<local-command-stdout>"
                            "installed plugin"
                            "</local-command-stdout>"
                        ),
                    },
                }
            ),
            # A genuine user prompt.
            json.dumps(
                {
                    "type": "user",
                    "uuid": "u-4",
                    "sessionId": "s-1",
                    "timestamp": "2026-01-15T10:00:03.000Z",
                    "message": {
                        "role": "user",
                        "content": "Hello, can you help me?",
                    },
                }
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "uuid": "a-1",
                    "sessionId": "s-1",
                    "timestamp": "2026-01-15T10:00:04.000Z",
                    "message": {
                        "id": "msg-1",
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Sure."}],
                    },
                }
            ),
        ]
    )
    title, _, messages = parse_cc_jsonl(text)
    # The two cleanable wrappers + the genuine prompt + the assistant reply.
    # The pure stdout-only message gets dropped.
    assert [m.role for m in messages] == ["human", "human", "human", "assistant"]
    assert messages[0].blocks[0].text == "/codex:setup --enable-review-gate"
    assert messages[1].blocks[0].text == "/plugin install codex"
    assert messages[2].blocks[0].text == "Hello, can you help me?"
    # Title comes from the first user message — the cleaned slash command.
    assert title == "/codex:setup --enable-review-gate"
    # No raw XML wrapper tag should leak into the title.
    assert "<command-" not in title


def test_cc_jsonl_slash_command_with_empty_args_omits_trailing_space():
    """A wrapper with empty <command-args> renders as just "/cmd"."""
    text = json.dumps(
        {
            "type": "user",
            "uuid": "u-1",
            "sessionId": "s-1",
            "timestamp": "2026-01-15T10:00:00.000Z",
            "message": {
                "role": "user",
                "content": (
                    "<command-message>codex:setup</command-message>\n"
                    "<command-name>/codex:setup</command-name>\n"
                    "<command-args></command-args>"
                ),
            },
        }
    )
    _, _, messages = parse_cc_jsonl(text)
    assert len(messages) == 1
    assert messages[0].blocks[0].text == "/codex:setup"


# ─── Codex JSONL ───────────────────────────────────────────


def test_codex_basic_shape(codex_text):
    title, created, messages = parse_codex_jsonl(codex_text)
    assert title == "Refactor parse_users in users.py to take a list of dicts."
    assert created.startswith("2026-01-15")
    # 2 user turns + 2 assistant bubbles (one per turn, with all assistant
    # text/reasoning/tool calls coalesced).
    assert len(messages) == 4
    assert [m.role for m in messages] == ["human", "assistant", "human", "assistant"]


def test_codex_filters_developer_and_environment_context(codex_text):
    _, _, messages = parse_codex_jsonl(codex_text)
    bodies = _bodies(messages)
    assert "permissions instructions" not in bodies
    assert "Approved command prefix saved" not in bodies
    assert "<environment_context>" not in bodies


def test_codex_assistant_uses_codex_role_label(codex_text):
    _, _, messages = parse_codex_jsonl(codex_text)
    assistants = [m for m in messages if m.role == "assistant"]
    assert all(m.role_label == "Codex" for m in assistants)


def test_codex_turn1_block_types(codex_text):
    """Turn 1 assistant: text, two parallel exec_command, thinking summary,
    text, apply_patch, pytest exec_command, final text."""
    _, _, messages = parse_codex_jsonl(codex_text)
    block_types = [type(b).__name__ for b in messages[1].blocks]
    # 4 ToolUseBlocks (3 exec_command + 1 apply_patch), 1 ThinkingBlock,
    # and 3 TextBlocks (intro, mid, closing).
    assert block_types.count("ToolUseBlock") == 4
    assert block_types.count("ThinkingBlock") == 1
    assert block_types.count("TextBlock") == 3
    # apply_patch is a custom_tool_call.
    tool_names = [b.name for b in messages[1].blocks if isinstance(b, ToolUseBlock)]
    assert tool_names.count("exec_command") == 3
    assert "apply_patch" in tool_names


def test_codex_function_call_paired_with_output(codex_text):
    _, _, messages = parse_codex_jsonl(codex_text)
    tools = [b for b in messages[1].blocks if isinstance(b, ToolUseBlock)]
    # All 4 tool calls in turn 1 had matching outputs.
    assert all(t.result is not None for t in tools)
    # The first exec_command was `ls users.py`.
    ls_tool = next(t for t in tools if t.input.get("cmd") == "ls users.py")
    assert "users.py" in ls_tool.result


def test_codex_renders_non_empty_reasoning_summary(codex_text):
    _, _, messages = parse_codex_jsonl(codex_text)
    # Turn 1 has exactly one non-empty ThinkingBlock.
    thinks = [b for b in messages[1].blocks if isinstance(b, ThinkingBlock)]
    assert len(thinks) == 1
    assert "the refactor is to define the new signature" in thinks[0].text
    # And it shows up in the rendered HTML.
    assistant_html = render_message(messages[1])
    assert "thinking" in assistant_html


def test_codex_filters_bundled_agents_md_and_env_context():
    """When Codex is launched with an AGENTS.md in the CWD, it bundles two
    input_text blocks into the first user message: an "# AGENTS.md
    instructions for ..." preamble and an <environment_context> block.
    Both are harness preamble and must be filtered at the block level —
    otherwise the AGENTS.md text leaks into the conversation and drives
    the page title.
    """
    text = "\n".join(
        [
            json.dumps(
                {
                    "timestamp": "2026-01-15T10:00:00.000Z",
                    "type": "session_meta",
                    "payload": {"id": "x", "cwd": "/Users/dev/projects/example"},
                }
            ),
            # First user message bundles AGENTS.md + env_context.
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
                                    "# AGENTS.md instructions for "
                                    "/Users/dev/projects/example\n\n"
                                    "<INSTRUCTIONS>\n@CLAUDE.md\n</INSTRUCTIONS>"
                                ),
                            },
                            {
                                "type": "input_text",
                                "text": (
                                    "<environment_context>\n"
                                    "  <cwd>/Users/dev/projects/example</cwd>\n"
                                    "</environment_context>"
                                ),
                            },
                        ],
                    },
                }
            ),
            # The genuine first user prompt.
            json.dumps(
                {
                    "timestamp": "2026-01-15T10:00:02.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "Why does this codebase use Alembic?",
                            }
                        ],
                    },
                }
            ),
            json.dumps(
                {
                    "timestamp": "2026-01-15T10:00:03.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Let me check.",
                            }
                        ],
                    },
                }
            ),
        ]
    )
    title, _, messages = parse_codex_jsonl(text)
    # The bundled-preamble user message is dropped entirely.
    assert [m.role for m in messages] == ["human", "assistant"]
    assert messages[0].blocks[0].text == "Why does this codebase use Alembic?"
    # Title comes from the genuine prompt, not from the AGENTS.md preamble.
    assert title == "Why does this codebase use Alembic?"
    bodies = "\n".join(render_message(m) for m in messages)
    assert "AGENTS.md instructions" not in bodies
    assert "<environment_context>" not in bodies


def test_codex_user_message_quoting_agents_md_in_one_block_is_kept():
    """A single user input_text block that *mentions* the AGENTS.md prefix
    with surrounding text must NOT be filtered — the per-block check
    requires the block to start with the prefix, but a block whose body
    is genuine prose discussing AGENTS.md still survives because it
    doesn't start with the literal "# AGENTS.md instructions for " token
    immediately. This is the symmetric case to the env_context regression."""
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
                                    "Have you seen the line "
                                    "`# AGENTS.md instructions for /tmp` in "
                                    "Codex output? What is that?"
                                ),
                            }
                        ],
                    },
                }
            ),
        ]
    )
    _, _, messages = parse_codex_jsonl(text)
    assert len(messages) == 1
    assert "Have you seen the line" in messages[0].blocks[0].text


def test_codex_user_message_with_leading_whitespace_before_agents_md_prefix_is_kept():
    """A user block whose body has leading whitespace before the literal
    AGENTS.md preamble token must NOT be filtered. Codex itself always
    emits the preamble at byte 0, so anything indented is not a harness
    injection — it's user prose (e.g. an indented code block quoting
    the preamble).
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
                                    "Look at this snippet:\n\n"
                                    "    # AGENTS.md instructions for /tmp\n"
                                    "    <INSTRUCTIONS>...</INSTRUCTIONS>\n\n"
                                    "Why does Codex emit it?"
                                ),
                            }
                        ],
                    },
                }
            ),
        ]
    )
    _, _, messages = parse_codex_jsonl(text)
    assert len(messages) == 1
    assert "Why does Codex emit it?" in messages[0].blocks[0].text


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
    assert messages[0].role == "human"
    assert isinstance(messages[0].blocks[0], TextBlock)
    assert "What does that block do?" in messages[0].blocks[0].text
    # Title comes from the first user prompt (truncated to 60 chars).
    assert title.startswith("Why does my prompt include")


def test_codex_unmatched_function_call_still_renders():
    """A function_call without a matching function_call_output should still
    appear as a ToolUseBlock with result=None."""
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
    assert len(messages) == 2
    tools = [b for b in messages[1].blocks if isinstance(b, ToolUseBlock)]
    assert len(tools) == 1
    assert tools[0].name == "exec_command"
    assert tools[0].result is None
    # And the rendered HTML still includes the tool name.
    assert "exec_command" in render_message(messages[1])
