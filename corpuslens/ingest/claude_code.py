"""Adapter: Claude Code session JSONL (one file per session, `timestamp` log
field per event line, `message.content` blocks). Point it at a directory; it
walks `**/*.jsonl`.

Provenance rule (non-negotiable, earned the hard way): dates come from the
`timestamp` LOG FIELD only — never from date-strings inside content. Content
dates once inflated a resumption count 10x.

Every line that fails to become an Event is COUNTED (`dropped`) and surfaced in
the audit sentence — nothing is silently discarded (review fix). Filenames are
hashed to opaque ids before they reach an Event, because export tools embed
dates and names in filenames.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from pathlib import Path

from ..model import AuthorClass, CoarseTime, DataType, Event, Quarantine, Surface
from . import register
from .injection import authored_text

ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T")

# CODE_REF: require CODE-ADJACENT context, not bare English words. The old
# pattern fired on "the company returns to profitability", "an Error in
# judgment", etc. Now every alternative needs a code shape: a call, a dotted
# call, a fence/backtick, a .py/type-annotation, a traceback line, or a
# keyword in a code-ish neighbourhood (followed by a symbol, not prose).
CODE_REF = re.compile(
    r"\b\w+\([^)]*\)"                       # a call: foo(...)
    r"|\b\w+\.\w+\("                         # a method call: obj.method(
    r"|`[^`]+`|```"                          # inline or fenced code
    r"|\.py\b|\.js\b|\.ts\b|\.rs\b|\.go\b"  # source file extensions
    r"|\bline\s+\d+\b"                       # "line 40"
    r"|Traceback \(most recent call last\)"
    r"|\b\w+Error\b|\bException\b"           # ValueError, KeyError, Exception
    r"|->|::|=>|\bself\.|\breturn\s+\w+\("   # code operators / return a call
    r"|\b(def|class|async def)\s+\w+\s*\("   # a real def/class WITH a param list
    r"|\bimport\s+\w+(\.\w+|\s+as\s+\w)"     # import a.b / import x as y (not "import goods")
    r"|\bfrom\s+[\w.]+\s+import\b",          # from x import y
    re.I,
)
# AUTHORED: pasted code. Fenced code, OR an indented keyword line, OR a bare
# assignment/def/return/import at low indent (unfenced paste is common in chat).
AUTHORED = re.compile(
    r"```"
    r"|^\s{2,}(def|class|for|if|elif|else|return|import|from|while|try|with)\b"
    r"|^\s*(def|class|import|from|async def)\s+\w"
    r"|^\s*[A-Za-z_]\w*\s*=\s*\S"           # x = something at line start
    r"|=>\s*\{|\bconsole\.log\(|\bprintln!\(",
    re.M,
)
DELIB = re.compile(
    r"\btalk (to me )?about\b|let'?s (talk|discuss|explore)|\bdiscuss\b|pros?\s*(and|/|\-)\s*cons?"
    r"|trade.?offs?|think (through|about)\b|what do you think|\bthoughts\b"
    r"|help me (think|understand|decide|figure|weigh)|walk me through|\boptions\b|brainstorm"
    r"|i'?m (thinking|wondering|considering)|convince me|push back", re.I)
CLARIFY = re.compile(
    r"do you (mean|want)|would you like|should i\b|which (one|of|do|would|approach)"
    r"|to clarify|can you confirm|just to confirm|one question|quick question", re.I)


def _hash(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8", "replace")).hexdigest()[:16]


def _features(text: str, stripped: bool) -> dict:
    return {
        "word_count": len(text.split()),
        "char_count": len(text),
        "code_fenced": text.count("```") >= 2,
        "code_authored": bool(AUTHORED.search(text)),
        "code_ref": bool(CODE_REF.search(text)),
        "delib": bool(DELIB.search(text)),
        "question": "?" in text,
        "clarify": bool(CLARIFY.search(text)),
        "injected_stripped": stripped,
    }


def _parse_ts(ts):
    if not (isinstance(ts, str) and ISO.match(ts)):
        return None, None
    d = datetime.date(int(ts[:4]), int(ts[5:7]), int(ts[8:10]))
    epoch = None
    try:
        epoch = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        pass
    return d, epoch


@register("claude-code")
def ingest(path: str, corpus_id: str = "corpus"):
    root = Path(path)
    # raw: (date, epoch|None, session_stem, role, text, real_ref)
    raw = []
    dropped = 0
    for f in sorted(root.rglob("*.jsonl")):
        session = f.stem
        with f.open(encoding="utf-8-sig", errors="replace") as fh:   # utf-8-sig: BOM-safe
            for i, ln in enumerate(fh):
                if not ln.strip():
                    continue
                try:
                    o = json.loads(ln)
                except Exception:
                    dropped += 1
                    continue
                if not isinstance(o, dict) or o.get("type") not in ("user", "assistant"):
                    dropped += 1                 # count non-dict / system / tool lines
                    continue
                d, epoch = _parse_ts(o.get("timestamp"))
                if d is None:
                    dropped += 1
                    continue
                msg = o.get("message") or {}
                content = msg.get("content")
                if isinstance(content, list):
                    text = " ".join(b.get("text") or "" for b in content
                                    if isinstance(b, dict) and b.get("type") == "text")
                else:
                    text = content if isinstance(content, str) else ""
                raw.append((d, epoch, session, o["type"], text, f"{f.name}:{i+1}"))

    if not raw:
        return [], Quarantine(), dropped

    base = min(r[0] for r in raw)                      # calendar anchor — quarantined
    # Sort per session CHRONOLOGICALLY before deltas/openers (log JSONL can be
    # non-monotonic across resume/branch). Undated epochs sort last, by line.
    by_session: dict = {}
    for rec in raw:
        by_session.setdefault(rec[2], []).append(rec)
    for recs in by_session.values():
        recs.sort(key=lambda r: (r[1] is None, r[1] if r[1] is not None else 0.0))

    events = []
    ref_map: dict = {}
    for session, recs in by_session.items():
        sid = _hash(corpus_id, session)
        prev_epoch = None
        for d, epoch, _, role, text, real_ref in recs:
            if role == "user":
                text, stripped = authored_text(text)
                author, dtype = AuthorClass.OPERATOR, DataType.PROMPT
            else:
                author, dtype, stripped = AuthorClass.MACHINE, DataType.RESPONSE, False
            if not text.strip():
                dropped += 1
                # empty turn still advances the chronological clock so the NEXT
                # delta is not silently bridged across it
                if epoch is not None:
                    prev_epoch = epoch
                continue
            delta = (epoch - prev_epoch) if (epoch is not None and prev_epoch is not None) else None
            if epoch is not None:
                prev_epoch = epoch
            opaque = _hash(sid, real_ref)
            ref_map[opaque] = real_ref
            events.append(Event(
                event_id=opaque, corpus_id=corpus_id, adapter_id="claude-code/1",
                source_ref=opaque, thread_id=sid, surface=Surface.CLI,
                author_class=author, data_type=dtype,
                time=CoarseTime(day_offset=(d - base).days, delta_prev_s=delta),
                features=_features(text, stripped)))
    return events, Quarantine(base_date_iso=base.isoformat(), ref_map=ref_map), dropped
