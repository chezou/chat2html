# chat2html

Convert Claude conversation logs into standalone static HTML files.

## Supported input formats (auto-detected)

1. **claude.ai export** (`conversations.json` / `.jsonl`)
   - Downloadable from Settings → Privacy → Export data (inside the ZIP).
   - Contains multiple conversations — pick them by listing, searching, or index.

2. **Claude Code session** (`~/.claude/projects/<proj>/*.jsonl`)
   - Line-based logs with `type` / `uuid` / `sessionId`.
   - Renders tool-use history (Bash / Read / Edit / Agent, etc.).
   - `thinking` blocks and long `tool_result` outputs are collapsed into `<details>`.

3. **claude-chat-exporter.js Markdown** (`.md`)
   - See <https://github.com/agarwalvishal/claude-chat-exporter>.
   - Uses `## Human (date):` / `## Claude:` headers.

## Quickstart

Run directly from the GitHub repository with `uv` — no install required:

```sh
uv run --from git+https://github.com/chezou/chat2html chat2html session.jsonl
```

The examples below use `chat2html` as shorthand for the command above.

## Usage

```sh
# Auto-detect format (Claude Code JSONL / Markdown)
chat2html session.jsonl
chat2html conversation.md
chat2html session.jsonl -o out.html

# claude.ai export: list conversations
chat2html conversations.json

# claude.ai export: search by title
chat2html conversations.json -s "API"

# claude.ai export: convert by index
chat2html conversations.json -i 0,3,7 -d out/

# claude.ai export: convert all
chat2html conversations.json --all -d out/

# Batch multiple files (Markdown / Claude Code JSONL)
chat2html a.md b.jsonl -d out/
```

## Options

| Option | Description |
| --- | --- |
| `-o`, `--output` | Output file path (single conversation only). |
| `-d`, `--outdir` | Output directory. |
| `-s`, `--search` | Search conversations by title (claude.ai export). |
| `-i`, `--index` | Comma-separated indices to convert (claude.ai export, e.g. `0,2,5`). |
| `--all` | Convert all conversations (claude.ai export). |
| `--lang {ja,en}` | Output language (default: `ja`). |
| `--full` | Show full tool input/output. By default, `tool_result` is omitted and `tool_use` only shows description-like fields for safer sharing. OAuth-related URLs are always masked, even with `--full`. |
