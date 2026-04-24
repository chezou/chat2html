"""Claude Code session JSONL parser.

Reads `~/.claude/projects/<proj>/*.jsonl` style logs into the IR. Handles
slash-command wrapper rewrites (turning the wrapper XML into a clean
`/cmd args` user message) and pairs `tool_use` blocks with their
matching `tool_result` from the next user record.
"""

import json
import re
from typing import Any

from ..i18n import t
from ..ir import Block, Message, TextBlock, ThinkingBlock, ToolUseBlock
from ..safety import _mask_oauth_urls
from ._common import _format_timestamp, _title_from_text

# Claude Code wraps slash-command invocations in user messages with these
# tags. The wrapper can lead with any of <command-message>, <command-name>,
# or <command-args> depending on how the command was invoked.
SLASH_COMMAND_RE = re.compile(r"^\s*<command-(?:name|message|args)>", re.DOTALL)
# Wrappers around local-command output (stdout/stderr/caveat).
LOCAL_COMMAND_RE = re.compile(
    r"^\s*<local-command-(?:caveat|stdout|stderr)>", re.DOTALL
)

_CC_COMMAND_NAME_RE = re.compile(
    r"<command-name>\s*(.*?)\s*</command-name>", re.DOTALL
)
_CC_COMMAND_ARGS_RE = re.compile(
    r"<command-args>\s*(.*?)\s*</command-args>", re.DOTALL
)


def _parse_cc_slash_command(text: str) -> str | None:
    """Extract a clean "/cmd args" string from a Claude Code slash-command
    wrapper.

    Returns None if the text is not a wrapper, or if it's a wrapper but no
    <command-name> tag is present (the latter happens for pure
    <local-command-stdout>/-stderr noise that we still want to drop).
    """
    if not (SLASH_COMMAND_RE.match(text) or LOCAL_COMMAND_RE.match(text)):
        return None
    name_match = _CC_COMMAND_NAME_RE.search(text)
    if not name_match:
        return None
    name = name_match.group(1).strip()
    if not name:
        return None
    args_match = _CC_COMMAND_ARGS_RE.search(text)
    args = args_match.group(1).strip() if args_match else ""
    return f"{name} {args}".strip()


def _stringify_tool_result_content(content: Any) -> str:
    """Flatten Claude Code's heterogeneous tool_result.content into a string
    suitable for storing on ToolUseBlock.result. OAuth URLs are masked here
    so the parser-side IR is already share-safe.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return _mask_oauth_urls(content)
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                parts.append(str(block))
                continue
            btype = block.get("type")
            if btype == "text":
                parts.append(block.get("text", ""))
            elif btype == "tool_reference":
                parts.append(f"- {block.get('tool_name', '')}")
            else:
                parts.append(json.dumps(block, ensure_ascii=False, indent=2))
        return _mask_oauth_urls("\n\n".join(p for p in parts if p))
    return _mask_oauth_urls(json.dumps(content, ensure_ascii=False, indent=2))


def parse_cc_jsonl(jsonl_text: str) -> tuple[str, str, list[Message]]:
    """Parse a Claude Code session JSONL."""
    records = []
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Lines that parse to non-dict would crash on rec.get(...) below.
        if isinstance(rec, dict):
            records.append(rec)

    # Map of tool_use_id -> tool_result.
    tool_results_by_id: dict[str, dict] = {}
    for rec in records:
        if rec.get("type") != "user":
            continue
        msg = rec.get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tid = block.get("tool_use_id")
                    if tid:
                        tool_results_by_id[tid] = block

    messages: list[Message] = []
    assistant_accum: dict[str, dict] = {}

    first_user_prompt = ""
    first_timestamp = ""
    session_id = ""

    for rec in records:
        rtype = rec.get("type")
        if not rtype:
            continue

        session_id = session_id or rec.get("sessionId", "")
        if not first_timestamp:
            first_timestamp = rec.get("timestamp", "")

        if rec.get("isMeta"):
            continue
        if rtype in ("file-history-snapshot", "last-prompt", "attachment"):
            continue
        if rtype == "system":
            continue

        if rtype == "user":
            msg = rec.get("message") or {}
            content = msg.get("content")
            timestamp = rec.get("timestamp", "")

            if isinstance(content, list):
                if all(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in content
                ):
                    continue

            if isinstance(content, str):
                if SLASH_COMMAND_RE.match(content) or LOCAL_COMMAND_RE.match(content):
                    cleaned = _parse_cc_slash_command(content)
                    if cleaned is None:
                        # Wrapper with no extractable <command-name> — pure
                        # output noise (e.g. bare <local-command-stdout>).
                        continue
                    content = cleaned
                if not first_user_prompt:
                    first_user_prompt = content
                messages.append(
                    Message(
                        role="human",
                        timestamp=timestamp,
                        blocks=[TextBlock(text=content)],
                    )
                )
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                text = "\n\n".join(p for p in text_parts if p)
                if text:
                    if not first_user_prompt:
                        first_user_prompt = text
                    messages.append(
                        Message(
                            role="human",
                            timestamp=timestamp,
                            blocks=[TextBlock(text=text)],
                        )
                    )

        elif rtype == "assistant":
            msg = rec.get("message") or {}
            mid = msg.get("id") or rec.get("uuid")
            timestamp = rec.get("timestamp", "")
            content = msg.get("content") or []

            if mid not in assistant_accum:
                assistant_accum[mid] = {
                    "timestamp": timestamp,
                    "raw_blocks": [],
                    "emitted_index": None,
                }
            entry = assistant_accum[mid]
            entry["raw_blocks"].extend(content if isinstance(content, list) else [])

            ir_blocks: list[Block] = []
            for raw in entry["raw_blocks"]:
                if not isinstance(raw, dict):
                    continue
                btype = raw.get("type")
                if btype == "thinking":
                    thinking_text = raw.get("thinking", "")
                    if thinking_text:
                        ir_blocks.append(ThinkingBlock(text=thinking_text))
                elif btype == "text":
                    text = raw.get("text", "")
                    if text:
                        ir_blocks.append(TextBlock(text=text))
                elif btype == "tool_use":
                    tid = raw.get("id")
                    tresult = tool_results_by_id.get(tid) if tid else None
                    result_str = (
                        _stringify_tool_result_content(tresult.get("content"))
                        if tresult is not None
                        else None
                    )
                    raw_input = raw.get("input")
                    tinput = raw_input if isinstance(raw_input, dict) else {}
                    ir_blocks.append(
                        ToolUseBlock(
                            name=raw.get("name", "tool"),
                            input=tinput,
                            result=result_str,
                        )
                    )

            if not ir_blocks:
                continue

            if entry["emitted_index"] is None:
                messages.append(
                    Message(
                        role="assistant",
                        timestamp=timestamp,
                        blocks=ir_blocks,
                    )
                )
                entry["emitted_index"] = len(messages) - 1
            else:
                messages[entry["emitted_index"]].blocks = ir_blocks
                messages[entry["emitted_index"]].timestamp = timestamp

    # Generate the title.
    title = t("default_title_cc")
    if first_user_prompt:
        title = _title_from_text(first_user_prompt) or title
    elif session_id:
        title = f"Session {session_id[:8]}"

    created = _format_timestamp(first_timestamp)
    return title, created, messages
