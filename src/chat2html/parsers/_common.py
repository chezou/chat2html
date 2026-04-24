"""Helpers shared by every parser."""

import re
from datetime import datetime

from ..safety import _mask_oauth_urls


def _format_timestamp(ts_str: str) -> str:
    """Format an ISO 8601 timestamp into a human-readable form."""
    if not ts_str:
        return ""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts_str


def _title_from_text(text: str, max_len: int = 60) -> str:
    """Build a one-line title from arbitrary text.

    Strips OAuth URLs first so they cannot leak into the page title,
    header, or any filename derived from it. Falls back to the empty
    string when the input is empty.
    """
    s = _mask_oauth_urls(text or "").strip().split("\n")[0]
    if len(s) > max_len:
        s = s[:max_len] + "…"
    return s


def _sanitize_filename(name: str) -> str:
    if not name:
        return "untitled"
    safe = re.sub(r'[<>:"/\\|?*]', "", name)
    safe = re.sub(r"\s+", "_", safe.strip())
    safe = safe[:120]
    return safe or "untitled"
