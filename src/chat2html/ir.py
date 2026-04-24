"""Intermediate representation for parsed conversations.

Parsers extract conversation content into Message objects whose `blocks`
describe the content as a sequence of typed blocks. The renderer then
turns Block instances into HTML. This decouples format-specific parsing
from format-agnostic rendering / safety-mode handling.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TextBlock:
    """Plain Markdown text from a user or assistant turn."""

    text: str


@dataclass
class ThinkingBlock:
    """Assistant reasoning, rendered collapsed."""

    text: str


@dataclass
class ToolUseBlock:
    """A tool invocation paired with its result, if any.

    `input` is the raw input dict (any shape).
    `result` is the raw result text or None when no paired output is available.
    Safe-mode redaction is applied at render time.
    """

    name: str
    input: dict
    result: str | None = None


Block = TextBlock | ThinkingBlock | ToolUseBlock


@dataclass
class Message:
    """One bubble in the conversation."""

    role: Literal["human", "assistant"]
    blocks: list[Block] = field(default_factory=list)
    timestamp: str = ""
    # Override the displayed role label (e.g. "Codex"). When None,
    # render_message() falls back to the i18n default for the role.
    role_label: str | None = None


# tool_use input fields safe to show even in share-safe mode
# (description-like fields that explain the tool's intent only).
SAFE_TOOL_USE_FIELDS = ("description", "subject", "subagent_type")
