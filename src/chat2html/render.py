"""HTML rendering for IR blocks/messages.

Holds the safe-mode toggle (`_FULL`); the CLI sets it from --full at startup.
Rendering is centralised here so each parser stays format-only and so safe
vs --full behaviour lives in one place.
"""

import html as html_mod
import json
import re

import bleach
import markdown

from .i18n import t
from .ir import (
    SAFE_TOOL_USE_FIELDS,
    Block,
    Message,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from .safety import _mask_oauth_urls

# Whether to show tool_result and sensitive tool_use input.
# Default (False) is share-safe mode; --full sets this to True.
_FULL: bool = False

# A tool_result longer than this collapses into a <details> with a length badge.
LONG_OUTPUT_THRESHOLD = 500

# Thresholds for detecting "pasted" content in user messages.
# Collapse when either the line count or the character count exceeds the limit.
USER_PASTE_LINES = 50
USER_PASTE_CHARS = 2000

_ALLOWED_HTML_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p",
    "br",
    "pre",
    "code",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "blockquote",
    "hr",
    "img",
}
_ALLOWED_HTML_ATTRIBUTES = {
    "a": ["href", "title"],
    "code": ["class"],
    "img": ["src", "alt", "title"],
}
_ALLOWED_HTML_PROTOCOLS = {"http", "https", "mailto"}

# Regex identifying fenced code blocks.
# Captures everything between ``` and ```. Also handles tilde fences.
_FENCED_CODE_RE = re.compile(r"(?ms)^(?P<fence>```|~~~)[^\n]*\n.*?^(?P=fence)\s*$")


def _render_md(text: str) -> str:
    if not text:
        return ""
    text = _mask_oauth_urls(text)
    rendered = markdown.markdown(text, extensions=["fenced_code", "tables", "nl2br"])
    return bleach.clean(
        rendered,
        tags=_ALLOWED_HTML_TAGS,
        attributes=_ALLOWED_HTML_ATTRIBUTES,
        protocols=_ALLOWED_HTML_PROTOCOLS,
        strip=True,
    )


def _render_code(text: str, lang: str = "") -> str:
    text = _mask_oauth_urls(text or "")
    escaped = html_mod.escape(text)
    cls = f' class="language-{lang}"' if lang else ""
    return f"<pre><code{cls}>{escaped}</code></pre>"


def _render_user_md(text: str) -> str:
    """Render Markdown for user messages.
    Long blobs outside code blocks (pasted content) are collapsed into <details>.

    Detection runs per sub-chunk, splitting non-code text on blank lines.
    This way, when prose and pasted data are interleaved, only the pasted
    portion gets collapsed.
    """
    if not text:
        return ""

    # Temporarily stash code blocks into placeholders.
    placeholders: list[str] = []

    def _stash(m: re.Match) -> str:
        placeholders.append(m.group(0))
        return f"\x00PASTE_STASH_{len(placeholders) - 1}\x00"

    stashed = _FENCED_CODE_RE.sub(_stash, text)

    # Split the remaining (non-code) text into chunks around placeholders.
    parts = re.split(r"(\x00PASTE_STASH_\d+\x00)", stashed)

    rendered: list[str] = []
    for part in parts:
        if not part:
            continue
        pm = re.fullmatch(r"\x00PASTE_STASH_(\d+)\x00", part)
        if pm:
            # Restore code blocks and render them as-is.
            rendered.append(_render_md(placeholders[int(pm.group(1))]))
            continue

        # Split non-code chunks on blank lines into sub-chunks.
        # Evaluate each sub-chunk independently:
        # collapse if long, render inline if short.
        subchunks = re.split(r"(\n\s*\n+)", part)
        for sub in subchunks:
            if not sub:
                continue
            # Pass through the blank-line separators untouched.
            if re.fullmatch(r"\n\s*\n+", sub):
                rendered.append(sub)
                continue

            trimmed = sub.strip("\n")
            line_count = trimmed.count("\n") + 1 if trimmed else 0
            char_count = len(trimmed)

            if trimmed and (
                line_count > USER_PASTE_LINES or char_count > USER_PASTE_CHARS
            ):
                summary_label = t("pasted_summary", lines=line_count, chars=char_count)
                escaped = html_mod.escape(_mask_oauth_urls(trimmed))
                badge = html_mod.escape(t("pasted_badge"))
                meta = html_mod.escape(summary_label)
                rendered.append(
                    f'<details class="pasted">'
                    f'<summary><span class="badge">{badge}</span>'
                    f'<span class="meta">{meta}</span></summary>'
                    f'<div class="body"><pre>{escaped}</pre></div>'
                    f"</details>"
                )
            else:
                rendered.append(_render_md(sub))

    return "".join(rendered)


def _short_preview(text: str, maxlen: int = 60) -> str:
    s = (text or "").replace("\n", " ").strip()
    s = _mask_oauth_urls(s)
    if len(s) > maxlen:
        s = s[:maxlen] + "…"
    return html_mod.escape(s)


def _render_thinking_block(thinking_text: str) -> str:
    if not thinking_text.strip():
        return ""
    preview = _short_preview(thinking_text, 80)
    body_html = _render_md(thinking_text)
    return (
        f'<details class="thinking">'
        f'<summary><span class="badge">thinking</span>'
        f'<span class="meta">{preview}</span></summary>'
        f'<div class="body">{body_html}</div>'
        f"</details>"
    )


def _render_tool_use_block(block: ToolUseBlock) -> str:
    name = block.name
    tinput = block.input if isinstance(block.input, dict) else {}

    # Build the preview shown in the summary.
    # Safe mode only looks at description-like fields.
    # --full falls back to a wider set of candidate keys.
    preview = ""
    if _FULL:
        candidate_keys = (
            "command",
            "description",
            "query",
            "subject",
            "file_path",
            "path",
            "subagent_type",
            "prompt",
            "pattern",
            "cmd",
        )
    else:
        candidate_keys = SAFE_TOOL_USE_FIELDS
    for key in candidate_keys:
        if key in tinput and tinput[key]:
            preview = _short_preview(str(tinput[key]), 80)
            break
    if _FULL and not preview and tinput:
        try:
            first_key = next(iter(tinput))
            preview = _short_preview(str(tinput[first_key]), 80)
        except StopIteration:
            pass

    # body: input and result
    body_parts: list[str] = []

    if _FULL:
        # Full input.
        input_pretty = json.dumps(tinput, ensure_ascii=False, indent=2)
        body_parts.append(_render_code(input_pretty, "json"))

        # Full tool_result.
        if block.result is not None:
            result_str = _mask_oauth_urls(block.result)
            if result_str:
                if len(result_str) > LONG_OUTPUT_THRESHOLD:
                    inner_preview = _short_preview(result_str, 80)
                    rendered = _render_md(result_str)
                    body_parts.append(
                        f'<details class="tool-result-long" open>'
                        f'<summary><span class="badge">result</span>'
                        f'<span class="meta">{len(result_str):,} chars — '
                        f"{inner_preview}</span></summary>"
                        f'<div class="body">{rendered}</div>'
                        f"</details>"
                    )
                else:
                    body_parts.append(
                        f'<div class="tool-result-inline">'
                        f"{html_mod.escape(result_str)}"
                        f"</div>"
                    )
    else:
        # ── safe mode ──
        # Only show description-like fields from tool_use input.
        safe_input = {
            k: tinput[k] for k in SAFE_TOOL_USE_FIELDS if k in tinput and tinput[k]
        }
        if safe_input:
            input_pretty = json.dumps(safe_input, ensure_ascii=False, indent=2)
            body_parts.append(_render_code(input_pretty, "json"))
        else:
            body_parts.append(
                f'<div class="tool-result-inline">'
                f"{html_mod.escape(t('omitted_input_label'))}"
                f"</div>"
            )
        # Always show only the omission message for tool_result.
        if block.result is not None:
            body_parts.append(
                f'<div class="tool-result-inline">'
                f'<span class="badge" style="background:var(--text-muted);'
                f'color:var(--bg);">{html_mod.escape(t("omitted_badge"))}</span> '
                f"{html_mod.escape(t('omitted_result_label'))}"
                f"</div>"
            )

    summary = (
        f'<summary><span class="badge">tool</span>'
        f'<span class="tool-name">{html_mod.escape(name)}</span>'
        f'<span class="meta">{preview}</span></summary>'
    )

    return (
        f'<details class="tool-call">'
        f"{summary}"
        f'<div class="body">{"".join(body_parts)}</div>'
        f"</details>"
    )


def render_block(block: Block, role: str = "assistant") -> str:
    """Render a single Block to HTML.

    The role is needed because user TextBlocks get paste-detection
    rendering, while assistant TextBlocks render straight Markdown.
    """
    if isinstance(block, TextBlock):
        if role == "human":
            return _render_user_md(block.text)
        return _render_md(block.text)
    if isinstance(block, ThinkingBlock):
        return _render_thinking_block(block.text)
    if isinstance(block, ToolUseBlock):
        return _render_tool_use_block(block)
    return ""


def render_message(msg: Message) -> str:
    if msg.role == "human":
        role_label = t("role_you")
    else:
        role_label = msg.role_label or t("role_claude")
    timestamp = html_mod.escape(msg.timestamp or "")
    body_html = "\n".join(render_block(b, msg.role) for b in msg.blocks)
    ts_html = f'<span class="timestamp">{timestamp}</span>' if timestamp else ""
    return (
        f'<div class="message {msg.role}">\n'
        f'  <div class="message-role">{role_label}{ts_html}</div>\n'
        f'  <div class="message-body">{body_html}</div>\n'
        f"</div>"
    )
