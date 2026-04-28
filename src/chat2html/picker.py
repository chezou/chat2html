"""TUI picker for selecting chat logs out of a directory.

Walks a directory for `.md` / `.jsonl` files, drops anything that doesn't
detect as a supported chat format, peeks the first user message for a
preview snippet, then renders a multi-select list via `pick` (an
optional `[tui]` extra). Previews are cached at
`~/.cache/chat2html/previews.json` keyed by path + mtime so repeated
runs over a big directory are instant.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import pick as _pick

from .format_detect import (
    FORMAT_CC_JSONL,
    FORMAT_CLAUDEAI,
    FORMAT_CODEX_JSONL,
    FORMAT_MD,
    detect_format,
)
from .parsers.claude_code import (
    LOCAL_COMMAND_RE,
    SLASH_COMMAND_RE,
    _parse_cc_slash_command,
)
from .parsers.codex import _codex_message_text
from .parsers.markdown import MD_HEADER_RE

# Extend pick's built-in select keys to also accept 'x'. pick already
# binds j/k for movement (alongside arrows), so adding x as a toggle
# lets users drive the picker entirely from the home row without
# reaching for Space.
_pick.KEYS_SELECT = (*_pick.KEYS_SELECT, ord("x"))

# Cap on how much of each file we read for detect + peek. Big enough to
# cover typical session preambles, small enough to keep walking a large
# directory snappy.
_HEAD_BYTES = 256 * 1024
_PEEK_MAX_LEN = 80
_VALID_EXTS = (".md", ".markdown", ".jsonl")
# Default cap on how many directory levels we descend from the root.
# Big enough to cover ~/.codex/sessions/YYYY/MM/DD/file.jsonl (4 levels)
# from `~/.codex`, but small enough that pointing at `~/.claude` doesn't
# unintentionally walk the whole home cache. Public so the CLI can reuse
# it for argparse defaults / help text.
DEFAULT_MAX_DEPTH = 5
# Default cap on how many entries we put in the picker. With 1 line per
# file, ~200 is still scannable; running uncapped over years of
# accumulated sessions can list thousands and slows the curses redraw.
DEFAULT_MAX_FILES = 200
# Bumped whenever fmt detection or peek logic changes so that previously
# cached previews (e.g. literal "/clear" snippets, or empty entries from
# an earlier "skip all slash commands" iteration) get re-derived.
_CACHE_VERSION = 3


@dataclass
class ChatFile:
    path: Path
    fmt: str
    mtime: float
    preview: str


def _read_head(path: Path, n_bytes: int = _HEAD_BYTES) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read(n_bytes)
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def _peek_cc_jsonl(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict) or rec.get("type") != "user":
            continue
        if rec.get("isMeta"):
            continue
        msg = rec.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            if SLASH_COMMAND_RE.match(content) or LOCAL_COMMAND_RE.match(content):
                cleaned = _parse_cc_slash_command(content)
                if cleaned is None:
                    continue
                # Bare slash command (no args) like `/clear`, `/compact`,
                # `/init` is housekeeping — skip and look for the next
                # real message. Slash commands with args (e.g.
                # `/asf-skills:stock-analysis 2025年のトヨタの株価推移`)
                # carry the user's actual intent, so use them.
                if " " not in cleaned:
                    continue
                return cleaned
            return content
        if isinstance(content, list):
            if all(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content
            ):
                continue
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            joined = "\n".join(p for p in parts if p)
            if joined:
                return joined
    return ""


def _peek_codex_jsonl(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict) or rec.get("type") != "response_item":
            continue
        payload = rec.get("payload") or {}
        if payload.get("type") != "message" or payload.get("role") != "user":
            continue
        out = _codex_message_text(payload.get("content"), drop_harness_blocks=True)
        if out:
            return out
    return ""


_MD_HUMAN_RE = re.compile(r"^##\s+Human(?:\s*\([^)]*\))?\s*:\s*$", re.MULTILINE)


def _peek_md(text: str) -> str:
    m = _MD_HUMAN_RE.search(text)
    if not m:
        return ""
    body = text[m.end() :]
    cut = re.search(r"^(##\s|---\s*$)", body, re.MULTILINE)
    if cut:
        body = body[: cut.start()]
    return body.strip()


def _one_line(s: str, max_len: int = _PEEK_MAX_LEN) -> str:
    s = (s or "").replace("\r", " ").strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


def _peek(text: str, fmt: str) -> str:
    if fmt == FORMAT_CC_JSONL:
        return _one_line(_peek_cc_jsonl(text))
    if fmt == FORMAT_CODEX_JSONL:
        return _one_line(_peek_codex_jsonl(text))
    if fmt == FORMAT_MD:
        return _one_line(_peek_md(text))
    return ""


def _cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "chat2html" / "previews.json"


def _load_cache() -> dict:
    try:
        with open(_cache_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict) or data.get("_version") != _CACHE_VERSION:
        return {}
    entries = data.get("entries")
    return entries if isinstance(entries, dict) else {}


def _save_cache(cache: dict) -> None:
    p = _cache_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(
                {"_version": _CACHE_VERSION, "entries": cache},
                f,
                ensure_ascii=False,
            )
    except OSError:
        pass


def walk_chat_files(
    root: Path,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_files: int = 0,
) -> tuple[list[ChatFile], int]:
    """Find chat-log files under `root`, sorted by mtime descending.

    Two-phase walk: phase 1 only does cheap `stat()` calls to collect
    candidates; phase 2 reads file heads (for fmt detection + preview)
    only on the surviving N. This way `max_files` saves real I/O when
    the user points at a tree with thousands of stale sessions.

    Filters by extension (`.md` / `.markdown` / `.jsonl`), then runs
    `detect_format` on each candidate to drop unrelated files (e.g. a
    project README that happens to be `.md`). claude.ai exports are
    also dropped — they belong to the single-file workflow.

    Args:
        root: directory to walk.
        max_depth: max recursion depth from `root`. `0` = root only
            (no recursion). Default `DEFAULT_MAX_DEPTH`, picked to
            cover both Claude Code and Codex layouts without blowing
            up when the user points at all of `~/.claude` or `~/.codex`.
        max_files: cap on the number of (most-recent) files we
            actually inspect for fmt detection + preview. `0` (default)
            disables the cap.

    Returns:
        `(items, dropped)` where `items` are validated ChatFiles
        (mtime-desc) and `dropped` counts files that matched the
        extension filter but were trimmed by `max_files` before fmt
        detection. Items that fail fmt detection are silently excluded
        and not counted in `dropped`.
    """
    # Phase 1: collect (path, mtime) using only cheap stat() calls.
    candidates: list[tuple[Path, float]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else len(Path(rel).parts)
        if depth >= max_depth:
            dirnames[:] = []
        else:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in _VALID_EXTS:
                continue
            path = Path(dirpath) / name
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size == 0:
                continue
            candidates.append((path, stat.st_mtime))

    # Phase 2: sort + cap before any expensive head reads.
    candidates.sort(key=lambda t: t[1], reverse=True)
    if max_files > 0 and len(candidates) > max_files:
        dropped = len(candidates) - max_files
        candidates = candidates[:max_files]
    else:
        dropped = 0

    # Phase 3: fmt detect + peek on the surviving N (cache-backed).
    cache = _load_cache()
    cache_dirty = False
    out: list[ChatFile] = []
    for path, mtime in candidates:
        key = str(path.resolve())
        entry = cache.get(key)
        fmt = ""
        preview = ""
        if isinstance(entry, dict) and entry.get("mtime") == mtime:
            cached_fmt = entry.get("fmt")
            if isinstance(cached_fmt, str):
                fmt = cached_fmt
                cached_preview = entry.get("preview")
                preview = cached_preview if isinstance(cached_preview, str) else ""
        if not fmt:
            head = _read_head(path)
            if not head.strip():
                continue
            fmt = detect_format(str(path), head)
            if fmt == FORMAT_CLAUDEAI:
                continue
            # `detect_format` returns FORMAT_MD for *any* `.md` file
            # by extension alone, so a stray README.md would otherwise
            # leak in. Reuse the markdown parser's strict header regex
            # (which requires the trailing colon) so docs like
            # `## Human resources` don't false-match.
            if fmt == FORMAT_MD and not MD_HEADER_RE.search(head):
                continue
            preview = _peek(head, fmt)
            cache[key] = {
                "mtime": mtime,
                "fmt": fmt,
                "preview": preview,
            }
            cache_dirty = True
        out.append(ChatFile(path=path, fmt=fmt, mtime=mtime, preview=preview))

    if cache_dirty:
        _save_cache(cache)
    return out, dropped


def _format_row(item: ChatFile, name_w: int) -> str:
    # Show the basename only, not the relative path: the parent dir adds
    # little signal in typical Claude Code / Codex layouts where every
    # session sits in the same dir. Truncate the *tail* so the head of
    # the filename (the meaningful prefix like a Codex `rollout-<date>`
    # timestamp) stays visible.
    name = item.path.name
    if len(name) > name_w:
        name = name[: name_w - 1] + "…"
    name = name.ljust(name_w)
    ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(item.mtime))
    return f"{name}  {ts}  {item.preview}"


def run_picker(items: list[ChatFile]) -> list[ChatFile]:
    """Show a multi-select picker; return the selected items."""
    if not items:
        return []
    name_w = min(40, max(len(i.path.name) for i in items))
    options = [_format_row(i, name_w) for i in items]
    title = (
        f"Select files to convert "
        f"(↑↓ move, Space/x toggle, Enter confirm, Esc/q quit) "
        f"— {len(items)} found"
    )
    # `pick` has no quit binding by default; wire q / Esc to abort.
    # In multiselect mode, hitting a quit key returns [] which the caller
    # treats as "user cancelled".
    selected = _pick.pick(
        options,
        title,
        multiselect=True,
        min_selection_count=1,
        indicator="→",
        quit_keys=(ord("q"), 27),
    )
    # multiselect returns list[(option, index)]; quit returns [].
    return [items[idx] for _, idx in selected]
