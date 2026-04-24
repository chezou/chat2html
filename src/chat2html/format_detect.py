"""Detect which input format a file is so the right parser is dispatched."""

import json
import os
import re

FORMAT_CC_JSONL = "cc_jsonl"  # Claude Code session
FORMAT_CLAUDEAI = "claudeai"  # claude.ai export (multiple conversations)
FORMAT_MD = "md"  # claude-chat-exporter Markdown
FORMAT_CODEX_JSONL = "codex_jsonl"  # OpenAI Codex CLI session

# Top-level `type` values that identify a Codex JSONL record.
_CODEX_TOP_TYPES = ("session_meta", "event_msg", "response_item", "turn_context")


def detect_format(path: str, text: str) -> str:
    """Detect the format from the extension and content."""
    ext = os.path.splitext(path)[1].lower()

    # Match by extension first.
    if ext in (".md", ".markdown"):
        return FORMAT_MD

    stripped = text.lstrip()
    if not stripped:
        return FORMAT_MD

    # Look inside the JSONL or JSON.
    first_line = stripped.split("\n", 1)[0].strip()

    # Try to parse the whole thing as JSON first.
    if stripped.startswith("["):
        try:
            arr = json.loads(stripped)
            if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                if "chat_messages" in arr[0]:
                    return FORMAT_CLAUDEAI
        except json.JSONDecodeError:
            pass

    # Try parsing each line as JSON.
    if first_line.startswith("{"):
        try:
            obj = json.loads(first_line)
            if isinstance(obj, dict):
                if "chat_messages" in obj:
                    return FORMAT_CLAUDEAI
                # Codex marker: top-level {timestamp, type, payload} with a known type.
                if (
                    obj.get("type") in _CODEX_TOP_TYPES
                    and isinstance(obj.get("payload"), dict)
                    and "uuid" not in obj
                    and "sessionId" not in obj
                ):
                    return FORMAT_CODEX_JSONL
                # Claude Code markers: type, uuid, sessionId
                if "sessionId" in obj or ("type" in obj and "uuid" in obj):
                    return FORMAT_CC_JSONL
                # Peek at the next ~20 records to decide. Use a bounded split
                # so we don't materialise every line of a multi-MB JSONL just
                # to sniff the format.
                for line in stripped.split("\n", 20)[:20]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        o = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(o, dict):
                        continue
                    if "chat_messages" in o:
                        return FORMAT_CLAUDEAI
                    if (
                        o.get("type") in _CODEX_TOP_TYPES
                        and isinstance(o.get("payload"), dict)
                        and "uuid" not in o
                        and "sessionId" not in o
                    ):
                        return FORMAT_CODEX_JSONL
                    if "sessionId" in o or ("type" in o and "uuid" in o):
                        return FORMAT_CC_JSONL
        except json.JSONDecodeError:
            pass

    # Detect by Markdown headers.
    if re.search(r"^##\s+(Human|Claude)", text, re.MULTILINE):
        return FORMAT_MD

    return FORMAT_MD
