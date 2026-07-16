"""Adapter: Cursor session JSONL (role/message lines; the runtime injects a
`<timestamp>` tag at the head of user text blocks and wraps the authored
query in `<user_query>`). Dates come from the injected tag at BLOCK START
only — a content-quoted tag mid-text does not count.

CONSERVATIVE BY CONSTRUCTION: only user turns whose text block starts with a
recognizable `<timestamp>` tag can be dated, so untagged turns and assistant
turns are dropped. Every such drop is COUNTED and surfaced in the audit
sentence (review fix — the old version silently discarded most of the corpus).
Filenames are hashed to opaque ids before reaching an Event.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from pathlib import Path

from ..model import AuthorClass, CoarseTime, DataType, Event, Quarantine, Surface
from . import register
from .claude_code import _features, _hash
from .injection import authored_text

MON = {m: i + 1 for i, m in enumerate((
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"))}
TAG = re.compile(r"^\s*<timestamp>\w+,\s+(\w+)\s+(\d{1,2}),\s+(\d{4})")


@register("cursor")
def ingest(path: str, corpus_id: str = "corpus"):
    root = Path(path)
    # raw: (date, session_stem, text, real_ref, stripped)
    raw = []
    dropped = 0
    for f in sorted(root.rglob("*.jsonl")):
        session = f.stem
        with f.open(encoding="utf-8-sig", errors="replace") as fh:
            for i, ln in enumerate(fh):
                if not ln.strip():
                    continue
                try:
                    o = json.loads(ln)
                except Exception:
                    dropped += 1
                    continue
                if not isinstance(o, dict) or o.get("role") != "user":
                    dropped += 1                 # assistant / system / non-dict
                    continue
                blocks = [b for b in (o.get("message") or {}).get("content") or []
                          if isinstance(b, dict) and b.get("type") == "text"]
                if not blocks:
                    dropped += 1
                    continue
                dated = False
                for blk in blocks:
                    txt = blk.get("text") or ""
                    m = TAG.match(txt)
                    if not m or m[1] not in MON:
                        continue
                    try:
                        d = datetime.date(int(m[3]), MON[m[1]], int(m[2]))
                    except ValueError:
                        continue
                    text, stripped = authored_text(txt)
                    if text:
                        raw.append((d, session, text, f"{f.name}:{i+1}", stripped))
                        dated = True
                if not dated:
                    dropped += 1                 # untagged user turn — counted, not hidden
    if not raw:
        return [], Quarantine(), dropped
    base = min(r[0] for r in raw)
    events = []
    ref_map: dict = {}
    for d, session, text, real_ref, stripped in raw:
        sid = _hash(corpus_id, session)
        opaque = _hash(sid, real_ref)
        ref_map[opaque] = real_ref
        events.append(Event(
            event_id=opaque, corpus_id=corpus_id, adapter_id="cursor/1",
            source_ref=opaque, thread_id=sid, surface=Surface.IDE,
            author_class=AuthorClass.OPERATOR, data_type=DataType.PROMPT,
            time=CoarseTime(day_offset=(d - base).days),
            features=_features(text, stripped)))
    return events, Quarantine(base_date_iso=base.isoformat(), ref_map=ref_map), dropped
