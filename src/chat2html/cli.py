"""Convert AI conversation logs to static HTML.

Supports claude.ai export, Claude Code JSONL, claude-chat-exporter Markdown,
and OpenAI Codex CLI JSONL.
See README.md for usage.
"""

import argparse
import os
import sys

from . import i18n, render
from .format_detect import (
    FORMAT_CC_JSONL,
    FORMAT_CLAUDEAI,
    FORMAT_CODEX_JSONL,
    FORMAT_MD,
    detect_format,
)
from .i18n import t
from .parsers import (
    load_claudeai_export,
    parse_cc_jsonl,
    parse_claudeai_conversation,
    parse_codex_jsonl,
    parse_markdown,
)
from .parsers._common import _format_timestamp, _sanitize_filename
from .template import to_html


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


def convert_single_file(input_path: str, output_path: str) -> None:
    """Convert a single Claude Code / Codex / Markdown conversation to one HTML file."""
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


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Convert AI conversation logs to HTML "
            "(claude.ai / Claude Code / claude-chat-exporter Markdown / Codex)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Claude Code / Codex session / Markdown (simple conversion)
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

    # Apply runtime settings to the modules that own them.
    i18n._LANG = args.lang
    render._FULL = args.full

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
            # Single conversation (Markdown / Claude Code JSONL / Codex JSONL)
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
