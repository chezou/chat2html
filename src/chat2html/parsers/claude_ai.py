"""Parser for the claude.ai conversation export.

The export is a JSON array (or JSONL) of conversations. Each conversation
has a `name`, `created_at`, and `chat_messages` array; this module loads
the file and parses one conversation at a time.
"""

import json

from ..i18n import t
from ..ir import Message, TextBlock
from ._common import _format_timestamp, _title_from_text


def load_claudeai_export(text: str) -> list[dict]:
    """Load either a JSON array or JSONL file of conversations."""
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass

    conversations = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            conversations.append(obj)
        except json.JSONDecodeError:
            continue
    return conversations


def _extract_claudeai_message_text(msg: dict) -> str:
    if "content" in msg and isinstance(msg["content"], list):
        parts = []
        for block in msg["content"]:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
        if parts:
            return "\n\n".join(parts)
    if msg.get("text"):
        return msg["text"]
    return ""


def parse_claudeai_conversation(conv: dict) -> tuple[str, str, list[Message]]:
    """Parse a single conversation from a claude.ai export."""
    raw_name = conv.get("name") or ""
    title = _title_from_text(raw_name, max_len=200) or t("default_conv_title")
    created = _format_timestamp(conv.get("created_at", ""))
    messages: list[Message] = []
    for msg in conv.get("chat_messages", []):
        sender = msg.get("sender", "unknown")
        role = "human" if sender == "human" else "assistant"
        ts = _format_timestamp(msg.get("created_at", ""))
        text = _extract_claudeai_message_text(msg)
        if not text.strip():
            continue
        messages.append(
            Message(role=role, timestamp=ts, blocks=[TextBlock(text=text)])
        )
    return title, created, messages
