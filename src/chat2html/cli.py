"""Convert AI conversation logs to static HTML.

Supports claude.ai export, Claude Code JSONL, claude-chat-exporter Markdown,
and OpenAI Codex CLI JSONL.
See README.md for usage.
"""

import argparse
import html as html_mod
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import bleach
import markdown

# ─── HTML template ──────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="{html_lang}" data-theme="auto">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  @import url('{font_url}');

  /* ── dark (default) ── */
  :root, :root[data-theme="dark"] {{
    --bg: #0f0f0f;
    --surface: #1a1a1a;
    --human-bg: #1e293b;
    --human-border: #3b82f6;
    --assistant-bg: #1a1a1a;
    --assistant-border: #525252;
    --text: #e4e4e7;
    --text-muted: #a1a1aa;
    --accent: #60a5fa;
    --code-bg: #0d0d0d;
    --border: #2a2a2a;
    --toggle-bg: #1a1a1a;
    --toggle-border: #2a2a2a;
    --tool-bg: #141414;
    --tool-border: #2a2a2a;
    --tool-accent: #a78bfa;
    --thinking-accent: #f59e0b;
  }}

  /* ── light ── */
  :root[data-theme="light"] {{
    --bg: #fafafa;
    --surface: #ffffff;
    --human-bg: #eff6ff;
    --human-border: #3b82f6;
    --assistant-bg: #ffffff;
    --assistant-border: #d4d4d8;
    --text: #18181b;
    --text-muted: #71717a;
    --accent: #2563eb;
    --code-bg: #f4f4f5;
    --border: #e4e4e7;
    --toggle-bg: #ffffff;
    --toggle-border: #e4e4e7;
    --tool-bg: #fafaf9;
    --tool-border: #e4e4e7;
    --tool-accent: #7c3aed;
    --thinking-accent: #d97706;
  }}

  /* ── auto: follow OS preference ── */
  @media (prefers-color-scheme: light) {{
    :root[data-theme="auto"] {{
      --bg: #fafafa;
      --surface: #ffffff;
      --human-bg: #eff6ff;
      --human-border: #3b82f6;
      --assistant-bg: #ffffff;
      --assistant-border: #d4d4d8;
      --text: #18181b;
      --text-muted: #71717a;
      --accent: #2563eb;
      --code-bg: #f4f4f5;
      --border: #e4e4e7;
      --toggle-bg: #ffffff;
      --toggle-border: #e4e4e7;
      --tool-bg: #fafaf9;
      --tool-border: #e4e4e7;
      --tool-accent: #7c3aed;
      --thinking-accent: #d97706;
    }}
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: {body_font};
    background: var(--bg);
    color: var(--text);
    line-height: 1.7;
    -webkit-font-smoothing: antialiased;
    transition: background 0.2s, color 0.2s;
  }}
  .theme-toggle {{
    position: fixed;
    top: 1rem;
    right: 1rem;
    z-index: 100;
    background: var(--toggle-bg);
    border: 1px solid var(--toggle-border);
    color: var(--text);
    width: 2.5rem;
    height: 2.5rem;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.1rem;
    transition: background 0.2s, border-color 0.2s, transform 0.1s;
    padding: 0;
  }}
  .theme-toggle:hover {{ transform: scale(1.05); }}
  .theme-toggle:active {{ transform: scale(0.95); }}
  .theme-toggle .icon-sun {{ display: none; }}
  .theme-toggle .icon-moon {{ display: block; }}
  :root[data-theme="light"] .theme-toggle .icon-sun {{ display: block; }}
  :root[data-theme="light"] .theme-toggle .icon-moon {{ display: none; }}
  @media (prefers-color-scheme: light) {{
    :root[data-theme="auto"] .theme-toggle .icon-sun {{ display: block; }}
    :root[data-theme="auto"] .theme-toggle .icon-moon {{ display: none; }}
  }}
  .header {{
    border-bottom: 1px solid var(--border);
    padding: 2rem 0;
    margin-bottom: 2rem;
  }}
  .header-inner {{
    max-width: 820px;
    margin: 0 auto;
    padding: 0 1.5rem;
  }}
  .header h1 {{
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin-bottom: 0.5rem;
  }}
  .header .meta {{
    color: var(--text-muted);
    font-size: 0.85rem;
  }}
  .header .meta span + span::before {{
    content: '·';
    margin: 0 0.5em;
  }}
  .conversation {{
    max-width: 820px;
    margin: 0 auto;
    padding: 0 1.5rem 4rem;
  }}
  .message {{
    margin-bottom: 1.5rem;
    border-radius: 8px;
    border-left: 3px solid transparent;
    padding: 1.25rem 1.5rem;
    position: relative;
    transition: background 0.2s, border-color 0.2s;
  }}
  .message.human {{
    background: var(--human-bg);
    border-left-color: var(--human-border);
  }}
  .message.assistant {{
    background: var(--assistant-bg);
    border-left-color: var(--assistant-border);
  }}
  .message-role {{
    font-size: 0.75rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin-bottom: 0.6rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }}
  .message.human .message-role {{ color: var(--accent); }}
  .message-role .timestamp {{
    font-weight: 400;
    letter-spacing: 0;
    text-transform: none;
    margin-left: auto;
    font-size: 0.7rem;
  }}
  .message-body {{ font-size: 0.95rem; }}
  .message-body p {{ margin-bottom: 0.8em; }}
  .message-body p:last-child {{ margin-bottom: 0; }}
  .message-body ul, .message-body ol {{
    padding-left: 1.5em;
    margin-bottom: 0.8em;
  }}
  .message-body li {{ margin-bottom: 0.3em; }}
  .message-body h1, .message-body h2, .message-body h3,
  .message-body h4, .message-body h5, .message-body h6 {{
    margin: 1.2em 0 0.5em;
    font-weight: 700;
    letter-spacing: -0.01em;
  }}
  .message-body h1 {{ font-size: 1.3rem; }}
  .message-body h2 {{ font-size: 1.15rem; }}
  .message-body h3 {{ font-size: 1.05rem; }}
  .message-body code {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85em;
    background: var(--code-bg);
    padding: 0.15em 0.4em;
    border-radius: 4px;
    border: 1px solid var(--border);
  }}
  .message-body pre {{
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1rem 1.25rem;
    overflow-x: auto;
    margin-bottom: 0.8em;
    line-height: 1.5;
  }}
  .message-body pre code {{
    background: none;
    border: none;
    padding: 0;
    font-size: 0.85rem;
  }}
  .message-body blockquote {{
    border-left: 3px solid var(--border);
    padding-left: 1em;
    color: var(--text-muted);
    margin-bottom: 0.8em;
  }}
  .message-body table {{
    border-collapse: collapse;
    width: 100%;
    margin-bottom: 0.8em;
    font-size: 0.9rem;
  }}
  .message-body th, .message-body td {{
    border: 1px solid var(--border);
    padding: 0.5em 0.75em;
    text-align: left;
  }}
  .message-body th {{
    background: var(--code-bg);
    font-weight: 500;
  }}
  .message-body a {{
    color: var(--accent);
    text-decoration: none;
  }}
  .message-body a:hover {{ text-decoration: underline; }}
  .message-body hr {{
    border: none;
    border-top: 1px solid var(--border);
    margin: 1.2em 0;
  }}
  .message-body img {{
    max-width: 100%;
    border-radius: 6px;
  }}

  /* ── thinking / tool blocks ── */
  details.thinking,
  details.tool-call,
  details.tool-result-long,
  details.pasted {{
    margin: 0.6em 0;
    border: 1px solid var(--tool-border);
    border-radius: 6px;
    background: var(--tool-bg);
    font-size: 0.88rem;
  }}
  details.thinking {{ border-left: 3px solid var(--thinking-accent); }}
  details.tool-call,
  details.tool-result-long {{ border-left: 3px solid var(--tool-accent); }}
  details.pasted {{ border-left: 3px solid var(--text-muted); }}
  details summary {{
    cursor: pointer;
    padding: 0.5em 0.9em;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: var(--text-muted);
    user-select: none;
    display: list-item;
  }}
  details summary:hover {{ color: var(--text); }}
  details summary .badge {{
    display: inline-block;
    padding: 0.1em 0.5em;
    border-radius: 3px;
    font-size: 0.7rem;
    margin-right: 0.4em;
    font-weight: 500;
  }}
  details.thinking summary .badge {{
    background: var(--thinking-accent);
    color: #fff;
  }}
  details.tool-call summary .badge {{
    background: var(--tool-accent);
    color: #fff;
  }}
  details.pasted summary .badge {{
    background: var(--text-muted);
    color: var(--bg);
  }}
  details summary .tool-name {{
    color: var(--text);
    font-weight: 500;
  }}
  details summary .meta {{
    color: var(--text-muted);
    margin-left: 0.4em;
  }}
  details[open] summary {{
    border-bottom: 1px solid var(--tool-border);
  }}
  details .body {{
    padding: 0.6em 0.9em 0.8em;
  }}
  details .body pre {{
    margin-bottom: 0.5em;
    font-size: 0.8rem;
  }}
  .tool-result-inline {{
    margin: 0.4em 0;
    padding: 0.5em 0.9em;
    background: var(--tool-bg);
    border: 1px solid var(--tool-border);
    border-left: 3px solid var(--tool-accent);
    border-radius: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: var(--text-muted);
    white-space: pre-wrap;
    word-break: break-word;
  }}

  .footer {{
    text-align: center;
    padding: 2rem;
    color: var(--text-muted);
    font-size: 0.75rem;
    border-top: 1px solid var(--border);
  }}
</style>
<!-- highlight.js (CDN): load both dark/light themes and toggle via JS -->
<link id="hljs-dark"
      rel="stylesheet"
      href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/atom-one-dark.min.css">
<link id="hljs-light"
      rel="stylesheet"
      disabled
      href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/atom-one-light.min.css">
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>
</head>
<body>
<button class="theme-toggle" id="themeToggle"
        aria-label="Toggle theme" title="Toggle theme">
  <span class="icon-sun">☀</span>
  <span class="icon-moon">☾</span>
</button>
<div class="header">
  <div class="header-inner">
    <h1>{title}</h1>
    <div class="meta">
      {meta_items}
    </div>
  </div>
</div>
<div class="conversation">
{messages}
</div>
<div class="footer">
  {footer_text}
</div>
<script>
(function() {{
  var root = document.documentElement;
  var btn = document.getElementById('themeToggle');
  var KEY = 'claude-chat-theme';
  var hljsDark = document.getElementById('hljs-dark');
  var hljsLight = document.getElementById('hljs-light');

  function applyHljsTheme() {{
    // Determine the effective theme (data-theme, falling back to prefers-color-scheme)
    var theme = root.getAttribute('data-theme');
    var effectiveDark;
    if (theme === 'light') {{
      effectiveDark = false;
    }} else if (theme === 'dark') {{
      effectiveDark = true;
    }} else {{
      // auto
      effectiveDark = !window.matchMedia('(prefers-color-scheme: light)').matches;
    }}
    if (hljsDark) hljsDark.disabled = !effectiveDark;
    if (hljsLight) hljsLight.disabled = effectiveDark;
  }}

  try {{
    var saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark') {{
      root.setAttribute('data-theme', saved);
    }}
  }} catch (e) {{}}

  // Follow OS theme changes when data-theme="auto"
  if (window.matchMedia) {{
    var mq = window.matchMedia('(prefers-color-scheme: light)');
    var listener = function() {{ applyHljsTheme(); }};
    if (mq.addEventListener) mq.addEventListener('change', listener);
    else if (mq.addListener) mq.addListener(listener);
  }}

  applyHljsTheme();

  btn.addEventListener('click', function() {{
    var current = root.getAttribute('data-theme');
    var next;
    if (current === 'auto') {{
      var prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;
      next = prefersLight ? 'dark' : 'light';
    }} else {{
      next = current === 'light' ? 'dark' : 'light';
    }}
    root.setAttribute('data-theme', next);
    try {{ localStorage.setItem(KEY, next); }} catch (e) {{}}
    applyHljsTheme();
  }});

  // Apply highlight.js to every <pre><code>
  if (window.hljs) {{
    document.querySelectorAll('pre code').forEach(function(block) {{
      window.hljs.highlightElement(block);
    }});
  }}
}})();
</script>
</body>
</html>
"""


# ─── i18n ──────────────────────────────────────────

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ja": {
        "html_lang": "ja",
        "font_url": "https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap",
        "body_font": "'Noto Sans JP', -apple-system, sans-serif",
        "footer_text": "Exported from claude.ai / Claude Code",
        "role_you": "You",
        "role_claude": "Claude",
        "role_codex": "Codex",
        "messages_label": "messages",
        "default_title_md": "Conversation with Claude",
        "default_title_cc": "Claude Code Session",
        "default_title_codex": "Codex Session",
        "default_conv_title": "Untitled",
        "cli_loaded": "読み込み: {n} 件の会話 ({path})",
        "cli_header_row": "{h:>4}  {m:>8}  {c:>16}  Title",
        "cli_hint": "変換するには -i <番号> または --all を指定してください。",
        "cli_out_of_range": "  スキップ: #{idx} は範囲外です（0-{last}）",
        "cli_err_no_conv": "エラー: 会話が見つかりませんでした。",
        "cli_err_not_found": "エラー: ファイルが見つかりません: {path}",
        "cli_err_invalid_index": "エラー: -i には数字をカンマ区切りで指定してください。",  # noqa: E501
        "cli_err_claudeai_format": "{path} は claude.ai エクスポート形式です。 -i / --all / -s を使ってください。",  # noqa: E501
        "cli_err_unsupported": "未対応の形式: {fmt}",
        "cli_done": "完了！",
        "omitted_badge": "omitted",
        "omitted_result_label": "結果は共有のため省略（--full で表示）",
        "omitted_input_label": "入力は共有のため省略（--full で表示）",
        "pasted_badge": "pasted",
        "pasted_summary": "{lines} 行 / {chars:,} 文字 を貼り付け",
    },
    "en": {
        "html_lang": "en",
        "font_url": "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap",
        "body_font": "'Inter', -apple-system, sans-serif",
        "footer_text": "Exported from claude.ai / Claude Code",
        "role_you": "You",
        "role_claude": "Claude",
        "role_codex": "Codex",
        "messages_label": "messages",
        "default_title_md": "Conversation with Claude",
        "default_title_cc": "Claude Code Session",
        "default_title_codex": "Codex Session",
        "default_conv_title": "Untitled",
        "cli_loaded": "Loaded {n} conversations ({path})",
        "cli_header_row": "{h:>4}  {m:>8}  {c:>16}  Title",
        "cli_hint": "Use -i <indices> or --all to convert.",
        "cli_out_of_range": "  Skipping #{idx}: out of range (0-{last})",
        "cli_err_no_conv": "Error: no conversations found.",
        "cli_err_not_found": "Error: file not found: {path}",
        "cli_err_invalid_index": "Error: -i requires comma-separated integers.",
        "cli_err_claudeai_format": "{path} is a claude.ai export. Use -i / --all / -s.",
        "cli_err_unsupported": "Unsupported format: {fmt}",
        "cli_done": "Done!",
        "omitted_badge": "omitted",
        "omitted_result_label": "Result omitted for sharing (use --full to show)",
        "omitted_input_label": "Input omitted for sharing (use --full to show)",
        "pasted_badge": "pasted",
        "pasted_summary": "{lines} lines / {chars:,} chars pasted",
    },
}

# Current language. Set from --lang in main().
_LANG: str = "ja"

# Whether to show tool_result and sensitive tool_use input.
# Default (False) is share-safe mode; --full sets this to True.
_FULL: bool = False

# tool_use fields safe to show even in share-safe mode
# (description-like fields that explain the tool's intent only).
SAFE_TOOL_USE_FIELDS = ("description", "subject", "subagent_type")


def t(key: str, **kwargs) -> str:
    """Look up a translated string, formatting with kwargs if given."""
    s = TRANSLATIONS[_LANG].get(key, key)
    return s.format(**kwargs) if kwargs else s


# ─── Intermediate representation (IR) ──────────────────────────────
#
# Parsers extract conversation content into Message objects whose `blocks`
# describe the content as a sequence of typed blocks. The renderer then
# turns Block instances into HTML. This decouples format-specific parsing
# from format-agnostic rendering / safety-mode handling.


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


# ─── Common utilities ──────────────────────────────────────────

# Regex that captures the whole URL.
# Trailing punctuation and closing brackets are excluded from the match.
_URL_RE = re.compile(r"https?://[^\s<>\"'`\\]+")

# If any of these parameter names appear in the query/fragment,
# treat the URL as OAuth-related.
_OAUTH_QUERY_KEYS = (
    "state",
    "code",
    "access_token",
    "id_token",
    "refresh_token",
    "client_secret",
    "code_challenge",
    "code_verifier",
    "redirect_uri",
    "authorization_code",
)

# If any of these markers appear in the path or host, treat the URL as OAuth-related.
_OAUTH_PATH_MARKERS = (
    "/oauth",
    "/authorize",
    "/authenticate",
    "/callback",
    "/auth/",
    "/login/oauth",
    "/o/oauth",
)

# Hostnames of well-known auth providers.
_OAUTH_HOSTS = (
    "accounts.google.com",
    "login.microsoftonline.com",
    "login.windows.net",
    "auth0.com",
    "okta.com",
    "login.salesforce.com",
)


def _is_oauth_url(url: str) -> bool:
    """Return True if the URL looks related to an OAuth auth flow."""
    lower = url.lower()

    # Check for OAuth parameters in the query/fragment.
    # Uses simple substring matching (does not parse the URL properly).
    qidx = lower.find("?")
    fidx = lower.find("#")
    boundary = (
        min(i for i in (qidx, fidx, len(lower)) if i >= 0)
        if (qidx >= 0 or fidx >= 0)
        else len(lower)
    )
    query_part = lower[boundary:]
    if query_part:
        for key in _OAUTH_QUERY_KEYS:
            # Match "?key=", "&key=", or "#key=" patterns.
            if (
                f"?{key}=" in query_part
                or f"&{key}=" in query_part
                or f"#{key}=" in query_part
            ):
                return True

    # Markers in the host/path.
    host_and_path = lower[:boundary]
    for marker in _OAUTH_PATH_MARKERS:
        if marker in host_and_path:
            return True

    # Known provider domains.
    for host in _OAUTH_HOSTS:
        if host in host_and_path:
            return True

    return False


# Replacement string used when masking.
_URL_REDACTED = "[redacted OAuth URL]"

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


def _mask_oauth_urls(text: str) -> str:
    """Replace OAuth-related URLs in the text with [redacted OAuth URL].
    Always applied to prevent accidental leaks.
    """
    if not text:
        return text

    # Punctuation that commonly trails a URL (covers both Japanese and English).
    _TRAILING_PUNCT = set(".,;:!?)]}>」』'\"")

    def _replace(m: re.Match) -> str:
        url = m.group(0)
        # Pull trailing punctuation back out of the URL match.
        trailing = ""
        while url and url[-1] in _TRAILING_PUNCT:
            trailing = url[-1] + trailing
            url = url[:-1]
        if _is_oauth_url(url):
            return _URL_REDACTED + trailing
        return url + trailing

    return _URL_RE.sub(_replace, text)


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


# Regex identifying fenced code blocks.
# Captures everything between ``` and ```. Also handles tilde fences.
_FENCED_CODE_RE = re.compile(r"(?ms)^(?P<fence>```|~~~)[^\n]*\n.*?^(?P=fence)\s*$")


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


def _format_timestamp(ts_str: str) -> str:
    """Format an ISO 8601 timestamp into a human-readable form."""
    if not ts_str:
        return ""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts_str


def _sanitize_filename(name: str) -> str:
    if not name:
        return "untitled"
    safe = re.sub(r'[<>:"/\\|?*]', "", name)
    safe = re.sub(r"\s+", "_", safe.strip())
    safe = safe[:120]
    return safe or "untitled"


# ─── Format detection ────────────────────────────────────────────────────

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
                # Peek at further records to decide.
                for line in stripped.split("\n")[:20]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        o = json.loads(line)
                    except json.JSONDecodeError:
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


# ─── Markdown parser ─────────────────────────────────────────────

MD_HEADER_RE = re.compile(
    r"^##\s+(Human|Claude)(?:\s*\(([^)]+)\))?\s*:\s*$",
    re.MULTILINE,
)


def parse_markdown(md_text: str) -> tuple[str, str, list[Message]]:
    """Return (title, created, messages)."""
    title = t("default_title_md")
    m = re.search(r"^#\s+(.+?)\s*$", md_text, re.MULTILINE)
    if m:
        title = m.group(1).strip()

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


# ─── claude.ai export parser ────────────────────────────────


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
    title = conv.get("name") or t("default_conv_title")
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


# ─── Claude Code JSONL parser ───────────────────────────────────

LONG_OUTPUT_THRESHOLD = 500

# Thresholds for detecting "pasted" content in user messages.
# Collapse when either the line count or the character count exceeds the limit.
USER_PASTE_LINES = 50
USER_PASTE_CHARS = 2000
SLASH_COMMAND_RE = re.compile(r"^\s*<command-name>", re.DOTALL)
LOCAL_CAVEAT_RE = re.compile(r"^\s*<local-command-caveat>", re.DOTALL)


def _stringify_tool_result_content(content: Any) -> str:
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


def parse_cc_jsonl(jsonl_text: str) -> tuple[str, str, list[dict]]:
    """Parse a Claude Code session JSONL."""
    records = []
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

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
                if SLASH_COMMAND_RE.match(content) or LOCAL_CAVEAT_RE.match(content):
                    continue
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
        preview = first_user_prompt.strip().split("\n")[0]
        if len(preview) > 60:
            preview = preview[:60] + "…"
        title = preview
    elif session_id:
        title = f"Session {session_id[:8]}"

    created = _format_timestamp(first_timestamp)
    return title, created, messages


# ─── Codex JSONL parser ───────────────────────────────────────


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


def _codex_message_text(content: Any) -> str:
    """Concatenate text from a Codex message.content (input_text/output_text blocks)."""
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") in ("input_text", "output_text"):
            parts.append(block.get("text", ""))
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


def parse_codex_jsonl(jsonl_text: str) -> tuple[str, str, list[dict]]:
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
            text = _codex_message_text(payload.get("content"))
            if not text:
                continue
            # System prompt + auto-approved-prefix notices live under "developer".
            if role == "developer":
                continue
            if role == "user":
                # Skip the harness <environment_context> injection. Match only
                # when the entire message *is* the env-context block, so that
                # a user quoting the tag with their own surrounding text
                # (e.g. asking about it) still goes through.
                stripped = text.strip()
                if (
                    stripped.startswith("<environment_context>")
                    and stripped.endswith("</environment_context>")
                ):
                    continue
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
        preview = first_user_prompt.strip().split("\n")[0]
        if len(preview) > 60:
            preview = preview[:60] + "…"
        title = preview
    elif session_id:
        title = f"Codex Session {session_id[:8]}"

    created = _format_timestamp(first_timestamp)
    return title, created, messages


# ─── Rendering ────────────────────────────────────────────────


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


def to_html(title: str, created: str, messages: list[Message]) -> str:
    messages_html = "\n".join(render_message(m) for m in messages)
    meta_parts = []
    if created:
        meta_parts.append(f"<span>{html_mod.escape(created)}</span>")
    meta_parts.append(
        f"<span>{len(messages)} {html_mod.escape(t('messages_label'))}</span>"
    )
    meta_items = "\n      ".join(meta_parts)
    return HTML_TEMPLATE.format(
        html_lang=t("html_lang"),
        font_url=t("font_url"),
        body_font=t("body_font"),
        footer_text=html_mod.escape(t("footer_text")),
        title=html_mod.escape(title),
        meta_items=meta_items,
        messages=messages_html,
    )


# ─── claude.ai list display ─────────────────────────────────────────


def print_claudeai_list(conversations: list, query: str | None = None):
    print()
    print(t("cli_header_row", h="#", m="Messages", c="Created"))
    print("─" * 70)
    for i, conv in enumerate(conversations):
        title = conv.get("name") or f"({t('default_conv_title')})"
        created = _format_timestamp(conv.get("created_at", ""))
        n_msgs = len(conv.get("chat_messages", []))
        if query and query.lower() not in title.lower():
            continue
        print(f"{i:>4}  {n_msgs:>8}  {created:>16}  {title}")
    print()


# ─── Per-file conversion ─────────────────────────────────────────


def convert_single_file(input_path: str, output_path: str) -> None:
    """Convert a single Claude Code JSONL / Markdown conversation to one HTML file."""
    with open(input_path, encoding="utf-8") as f:
        text = f.read()

    fmt = detect_format(input_path, text)

    if fmt == FORMAT_MD:
        title, created, messages = parse_markdown(text)
    elif fmt == FORMAT_CC_JSONL:
        title, created, messages = parse_cc_jsonl(text)
    elif fmt == FORMAT_CODEX_JSONL:
        title, created, messages = parse_codex_jsonl(text)
    elif fmt == FORMAT_CLAUDEAI:
        # claude.ai export contains multiple conversations, so hitting this
        # branch means the caller should have used handle_claudeai_export.
        raise RuntimeError(t("cli_err_claudeai_format", path=input_path))
    else:
        raise RuntimeError(t("cli_err_unsupported", fmt=fmt))

    html = to_html(title, created, messages)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✓ {input_path} → {output_path} ({fmt}, {len(messages)} msgs)")


def handle_claudeai_export(
    input_path: str,
    text: str,
    args: argparse.Namespace,
) -> None:
    """Handle a claude.ai export (list / search / selective conversion)."""
    conversations = load_claudeai_export(text)
    if not conversations:
        print(t("cli_err_no_conv"), file=sys.stderr)
        sys.exit(1)

    print(t("cli_loaded", n=len(conversations), path=input_path))

    # List or search mode.
    if args.search or (not args.index and not args.all):
        print_claudeai_list(conversations, args.search)
        if not args.index and not args.all:
            print(t("cli_hint"))
        return

    # Decide which conversations to convert.
    if args.all:
        indices = list(range(len(conversations)))
    else:
        try:
            indices = [int(x.strip()) for x in args.index.split(",")]
        except ValueError:
            print(t("cli_err_invalid_index"), file=sys.stderr)
            sys.exit(1)

    outdir = args.outdir or args.output or "."
    # If -o looks like a file name (.html) and there is exactly one item,
    # treat it as a direct file path.
    single_file_out = None
    if args.output and args.output.endswith(".html") and len(indices) == 1:
        single_file_out = args.output
    else:
        os.makedirs(outdir, exist_ok=True)

    for idx in indices:
        if idx < 0 or idx >= len(conversations):
            print(t("cli_out_of_range", idx=idx, last=len(conversations) - 1))
            continue
        conv = conversations[idx]
        title, created, messages = parse_claudeai_conversation(conv)

        if single_file_out:
            filepath = single_file_out
        else:
            filename = (
                _sanitize_filename(conv.get("name") or t("default_conv_title"))
                + ".html"
            )
            filepath = os.path.join(outdir, filename)

        html = to_html(title, created, messages)
        os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  ✓ #{idx} → {filepath} ({len(messages)} msgs)")


# ─── Main ─────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Convert Claude conversation logs to HTML (3 formats supported)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Claude Code session / Markdown (simple conversion)
  chat2html session.jsonl
  chat2html conversation.md -o out.html
  chat2html a.md b.jsonl -d out/

  # claude.ai export (JSON/JSONL containing multiple conversations)
  chat2html conversations.json              # list conversations
  chat2html conversations.json -s "API"     # search by title
  chat2html conversations.json -i 0,3,7 -d out/
  chat2html conversations.json --all -d out/
""",
    )
    parser.add_argument("files", nargs="+", help=".md / .jsonl / .json file(s)")
    parser.add_argument(
        "-o", "--output", help="output file path (single conversation only)"
    )
    parser.add_argument("-d", "--outdir", help="output directory")
    parser.add_argument("-s", "--search", help="search by title (claude.ai export)")
    parser.add_argument(
        "-i",
        "--index",
        help=(
            "indices of conversations to convert "
            "(claude.ai export, comma-separated: 0,2,5)"
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="convert all conversations (claude.ai export)",
    )
    parser.add_argument(
        "--lang",
        choices=["ja", "en"],
        default="ja",
        help="output language (default: ja)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help=(
            "show full tool input/output. By default tool_result is omitted for safer "
            "sharing and tool_use only shows description-like fields. "
            "OAuth-related URLs are always masked, even with --full."
        ),
    )

    args = parser.parse_args()

    # Apply language settings.
    global _LANG, _FULL
    _LANG = args.lang
    _FULL = args.full

    # Verify files exist.
    for fp in args.files:
        if not os.path.exists(fp):
            print(t("cli_err_not_found", path=fp), file=sys.stderr)
            sys.exit(1)

    # Detect and process each file one by one.
    for input_path in args.files:
        with open(input_path, encoding="utf-8") as f:
            text = f.read()
        fmt = detect_format(input_path, text)

        if fmt == FORMAT_CLAUDEAI:
            # claude.ai exports are processed independently, one file at a time.
            handle_claudeai_export(input_path, text, args)
        else:
            # Single conversation (Markdown / Claude Code JSONL)
            if len(args.files) == 1 and not args.outdir:
                output_path = args.output or (os.path.splitext(input_path)[0] + ".html")
            else:
                outdir = args.outdir or "."
                os.makedirs(outdir, exist_ok=True)
                base = os.path.splitext(os.path.basename(input_path))[0]
                output_path = os.path.join(outdir, base + ".html")
            convert_single_file(input_path, output_path)

    print(t("cli_done"))


if __name__ == "__main__":
    main()
