"""OAuth URL detection and masking.

Always applied at render-time and again at title-generation time, so that
an OAuth URL in conversation content (especially the first user prompt,
which feeds the page title) cannot leak into the exported HTML.
"""

import re

# Regex that captures the whole URL.
# This deliberately allows trailing punctuation/closing brackets to match
# (since URLs can legitimately contain them); _mask_oauth_urls() then peels
# common trailing punctuation back off the end before deciding whether to
# redact, so e.g. "see https://x/oauth/cb?state=y." keeps the period
# outside the redacted span.
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

# Replacement string used when masking.
_URL_REDACTED = "[redacted OAuth URL]"


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
