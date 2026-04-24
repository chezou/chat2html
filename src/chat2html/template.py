"""Outer HTML template + to_html() entry that wires it all together."""

import html as html_mod

from .i18n import t
from .ir import Message
from .render import render_message

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
