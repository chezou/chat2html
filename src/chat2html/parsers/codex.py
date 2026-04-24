"""OpenAI Codex CLI session JSONL parser.

Each record is `{timestamp, type, payload}`. Conversation content lives
in `response_item` records; `event_msg` and `turn_context` are auxiliary
and mostly skipped. Tool calls (function_call + custom_tool_call) are
paired with their outputs by `call_id`. Harness preamble bundled into
the first user message (env_context, AGENTS.md auto-load) is filtered
at the block level.
"""

import json
from typing import Any

from ..i18n import t
from ..ir import Block, Message, TextBlock, ThinkingBlock, ToolUseBlock
from ._common import _format_timestamp, _title_from_text


def _extract_codex_outputs(records: list[dict]) -> dict[str, str]:
    """Build a {call_id: output_text} map from function/custom tool outputs.

    `custom_tool_call_output.output` is a JSON string like {"output": "..."}.
    """
    outputs: dict[str, str] = {}
    for rec in records:
        if rec.get("type") != "response_item":
            continue
        payload = rec.get("payload") or {}
        ptype = payload.get("type")
        call_id = payload.get("call_id")
        if not call_id:
            continue
        if ptype == "function_call_output":
            outputs[call_id] = payload.get("output", "") or ""
        elif ptype == "custom_tool_call_output":
            raw = payload.get("output", "") or ""
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and "output" in parsed:
                    outputs[call_id] = str(parsed["output"])
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
            outputs[call_id] = raw
    return outputs


# Prefix Codex prepends to the bundled-in AGENTS.md contents when the CWD
# has an AGENTS.md file. The full text looks like:
#   "# AGENTS.md instructions for <abs path>\n\n<INSTRUCTIONS>...</INSTRUCTIONS>"
_CODEX_AGENTS_MD_PREFIX = "# AGENTS.md instructions for "


def _codex_text_block_is_harness_injection(text: str) -> bool:
    """True for an input_text block that's a Codex harness injection
    (env_context preamble or AGENTS.md auto-load), not actual user content.

    Codex bundles these into the first user message's content array as
    extra input_text blocks. We filter them at the block level so a
    bundled message doesn't slip through whole just because one block
    happens to be the genuine prompt.

    Whitespace handling differs between the two wrapper kinds on purpose:
    - The env_context wrapper is matched after `strip()` because the XML
      payload may have trailing newlines.
    - The AGENTS.md preamble is matched against the original `text`
      (no leading-whitespace tolerance) because Codex always emits the
      preamble at byte 0 of its injected block; insisting on a strict
      prefix avoids dropping user prose that happens to begin with
      whitespace followed by the literal token.
    """
    s = text.strip()
    if not s:
        return True
    if s.startswith("<environment_context>") and s.endswith("</environment_context>"):
        return True
    if text.startswith(_CODEX_AGENTS_MD_PREFIX):
        return True
    return False


def _codex_message_text(content: Any, *, drop_harness_blocks: bool = False) -> str:
    """Concatenate text from a Codex message.content (input_text/output_text blocks).

    When `drop_harness_blocks=True`, individual blocks that look like Codex
    harness injections (AGENTS.md auto-load, environment_context wrapper)
    are filtered out before joining. Use this for user messages; assistant
    output_text never contains harness injections.
    """
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") in ("input_text", "output_text"):
            text = block.get("text", "")
            if drop_harness_blocks and _codex_text_block_is_harness_injection(text):
                continue
            parts.append(text)
    return "\n\n".join(p for p in parts if p)


def _codex_reasoning_text(payload: dict) -> str:
    """Extract human-readable text from a Codex reasoning record's `summary`.

    `summary` is often `[]` (encrypted reasoning only); in that case we have
    nothing to show.
    """
    summary = payload.get("summary") or []
    parts = []
    for s in summary:
        if isinstance(s, dict):
            parts.append(s.get("text", ""))
        elif isinstance(s, str):
            parts.append(s)
    return "\n\n".join(p for p in parts if p)


def parse_codex_jsonl(jsonl_text: str) -> tuple[str, str, list[Message]]:
    """Parse an OpenAI Codex CLI session JSONL.

    Format: each line is `{timestamp, type, payload}`. Conversation content
    lives in `response_item` records; `event_msg` and `turn_context` are
    auxiliary and mostly skipped.
    """
    records = []
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    outputs_by_call_id = _extract_codex_outputs(records)

    messages: list[Message] = []
    first_user_prompt = ""
    first_timestamp = ""
    session_id = ""

    # Codex emits assistant text, reasoning, and tool calls as separate
    # response_items. We coalesce them into one assistant bubble until a user
    # message arrives.
    pending_blocks: list[Block] = []
    pending_ts = ""
    codex_role_label = t("role_codex")

    def flush_assistant() -> None:
        nonlocal pending_blocks, pending_ts
        if pending_blocks:
            messages.append(
                Message(
                    role="assistant",
                    timestamp=pending_ts,
                    blocks=list(pending_blocks),
                    role_label=codex_role_label,
                )
            )
        pending_blocks = []
        pending_ts = ""

    for rec in records:
        rtype = rec.get("type")
        timestamp = rec.get("timestamp", "")
        if not first_timestamp:
            first_timestamp = timestamp

        if rtype == "session_meta":
            session_id = session_id or (rec.get("payload") or {}).get("id", "")
            continue

        # Skip event_msg / turn_context / unknown.
        if rtype != "response_item":
            continue

        payload = rec.get("payload") or {}
        ptype = payload.get("type")

        if ptype == "message":
            role = payload.get("role")
            # System prompt + auto-approved-prefix notices live under "developer".
            if role == "developer":
                continue
            # For user messages, drop harness-injected blocks
            # (env_context, AGENTS.md auto-load) before joining; if nothing
            # remains, the message was pure harness preamble and can be
            # skipped. A user message that *quotes* one of those tags with
            # surrounding text in the same block still survives, because
            # the per-block check requires the whole block to be the
            # wrapper.
            text = _codex_message_text(
                payload.get("content"),
                drop_harness_blocks=(role == "user"),
            )
            if not text:
                continue
            if role == "user":
                flush_assistant()
                if not first_user_prompt:
                    first_user_prompt = text
                messages.append(
                    Message(
                        role="human",
                        timestamp=timestamp,
                        blocks=[TextBlock(text=text)],
                    )
                )
            elif role == "assistant":
                if not pending_ts:
                    pending_ts = timestamp
                pending_blocks.append(TextBlock(text=text))

        elif ptype == "reasoning":
            summary_text = _codex_reasoning_text(payload)
            if summary_text.strip():
                if not pending_ts:
                    pending_ts = timestamp
                pending_blocks.append(ThinkingBlock(text=summary_text))

        elif ptype in ("function_call", "custom_tool_call"):
            name = payload.get("name", "tool")
            call_id = payload.get("call_id", "")
            if ptype == "function_call":
                args_raw = payload.get("arguments", "")
                try:
                    args = (
                        json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                    )
                    if not isinstance(args, dict):
                        args = {"input": args}
                except json.JSONDecodeError:
                    args = {"input": args_raw}
            else:
                # custom_tool_call.input is a free-form string (e.g. patch text).
                input_value = payload.get("input", "")
                args = (
                    {"input": input_value}
                    if not isinstance(input_value, dict)
                    else input_value
                )
            output_text = outputs_by_call_id.get(call_id, "") or None
            if not pending_ts:
                pending_ts = timestamp
            pending_blocks.append(
                ToolUseBlock(name=name, input=args, result=output_text)
            )

        # function_call_output / custom_tool_call_output were already paired
        # via outputs_by_call_id.

    flush_assistant()

    title = t("default_title_codex")
    if first_user_prompt:
        title = _title_from_text(first_user_prompt) or title
    elif session_id:
        title = f"Codex Session {session_id[:8]}"

    created = _format_timestamp(first_timestamp)
    return title, created, messages
