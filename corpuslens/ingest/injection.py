"""Injection filter — operator-typed vs machine-injected.

Cross-runtime comparison is corrupted by injected context (the Cursor
front-loading finding, 2026-07-16: median 3202w -> 15w once stripped). This
filter is applied at ingest so nothing downstream ever mistakes tooling for a
person. Regexes are conservative: strip only wrappers KNOWN to be injected.
"""
from __future__ import annotations

import re

INJECTED = re.compile(
    r"<user_info>.*?</user_info>"
    r"|<system-reminder>.*?</system-reminder>"
    r"|<environment_details>.*?</environment_details>"
    r"|<additional_data>.*?</additional_data>"
    r"|<timestamp>.*?</timestamp>",
    re.DOTALL | re.IGNORECASE,
)
USER_QUERY = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)


def authored_text(raw: str) -> tuple[str, bool]:
    """Return (operator-authored text, was_anything_stripped)."""
    stripped = False
    m = USER_QUERY.findall(raw)
    if m:
        raw = " ".join(m)
        stripped = True
    cleaned = INJECTED.sub(" ", raw)
    if cleaned != raw:
        stripped = True
    return cleaned.strip(), stripped
