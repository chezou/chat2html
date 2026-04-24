"""claude-chat-exporter Markdown parser.

Format: a `# Title` line followed by `## Human (timestamp):` /
`## Claude:` headers, separated by `---` between turns.
"""

import re

from ..i18n import t
from ..ir import Message, TextBlock
from ._common import _title_from_text

MD_HEADER_RE = re.compile(
    r"^##\s+(Human|Claude)(?:\s*\(([^)]+)\))?\s*:\s*$",
    re.MULTILINE,
)


def parse_markdown(md_text: str) -> tuple[str, str, list[Message]]:
    """Return (title, created, messages)."""
    title = t("default_title_md")
    m = re.search(r"^#\s+(.+?)\s*$", md_text, re.MULTILINE)
    if m:
        title = _title_from_text(m.group(1), max_len=200) or title

    messages: list[Message] = []
    matches = list(MD_HEADER_RE.finditer(md_text))
    created = ""
    for i, match in enumerate(matches):
        role_raw = match.group(1)
        timestamp = match.group(2) or ""
        role = "human" if role_raw == "Human" else "assistant"

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        body = md_text[start:end]
        body = re.sub(r"\n---\s*\n*\s*$", "\n", body).strip()
        if not body:
            continue

        if not created and timestamp and role == "human":
            created = timestamp

        messages.append(
            Message(role=role, timestamp=timestamp, blocks=[TextBlock(text=body)])
        )

    return title, created, messages
