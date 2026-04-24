"""Translation strings + lookup.

Holds the global `_LANG` selector. The CLI sets it from --lang at startup;
all other modules read it indirectly via `t()`.
"""

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ja": {
        "html_lang": "ja",
        "font_url": "https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap",
        "body_font": "'Noto Sans JP', -apple-system, sans-serif",
        "footer_text": "Exported from claude.ai / Claude Code / Codex",
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
        "footer_text": "Exported from claude.ai / Claude Code / Codex",
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

# Current language. The CLI sets this from --lang at startup.
_LANG: str = "ja"


def t(key: str, **kwargs) -> str:
    """Look up a translated string, formatting with kwargs if given."""
    s = TRANSLATIONS[_LANG].get(key, key)
    return s.format(**kwargs) if kwargs else s
