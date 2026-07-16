"""Adapter: Cursor session JSONL (role/message lines; the runtime injects a
`<timestamp>` tag at the head of user text blocks and wraps the authored
query in `<user_query>`). Dates come from the injected tag at BLOCK START
only — a content-quoted tag mid-text does not count."""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from ..model import AuthorClass, CoarseTime, DataType, Event, Quarantine, Surface
from . import register
from .claude_code import _features
from .injection import authored_text

MON = {m: i + 1 for i, m in enumerate((
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"))}
TAG = re.compile(r"^\s*<timestamp>\w+,\s+(\w+)\s+(\d{1,2}),\s+(\d{4})")


@register("cursor")
def ingest(path: str, corpus_id: str = "corpus"):
    root = Path(path)
    raw = []
    dropped = 0
    for f in sorted(root.rglob("*.jsonl")):
        session = f.stem
        for i, ln in enumerate(f.open(errors="replace")):
            try:
                o = json.loads(ln)
            except Exception:
                dropped += 1
                continue
            if not isinstance(o, dict) or o.get("role") != "user":
                continue
            for blk in (o.get("message") or {}).get("content") or []:
                if not isinstance(blk, dict) or blk.get("type") != "text":
                    continue
                txt = blk.get("text") or ""
                m = TAG.match(txt)
                if not m or m[1] not in MON:
                    continue
                try:
                    d = datetime.date(int(m[3]), MON[m[1]], int(m[2]))
                except ValueError:
                    dropped += 1
                    continue
                text, stripped = authored_text(txt)
                if text:
                    raw.append((d, session, text, f"{f.name}:{i+1}", stripped))
    if not raw:
        return [], Quarantine(), dropped
    base = min(r[0] for r in raw)
    events = [Event(
        event_id=f"{s}:{ref}", corpus_id=corpus_id, adapter_id="cursor/1",
        source_ref=ref, thread_id=s, surface=Surface.IDE,
        author_class=AuthorClass.OPERATOR, data_type=DataType.PROMPT,
        time=CoarseTime(day_offset=(d - base).days),
        features=_features(t, stripped)) for d, s, t, ref, stripped in raw]
    return events, Quarantine(base_date_iso=base.isoformat()), dropped
