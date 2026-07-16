"""Adapter: Claude Code session JSONL (one file per session, `timestamp` log
field per event line, `message.content` blocks). Point it at a directory; it
walks `**/*.jsonl`.

Provenance rule (non-negotiable, earned the hard way): dates come from the
`timestamp` LOG FIELD only — never from date-strings inside content. Content
dates once inflated a resumption count 10x.

Robustness rules (every one earned in review):
  * Every line that fails to become an Event is COUNTED (`dropped`) and
    surfaced in the audit sentence — nothing silently discarded.
  * A single malformed line or an unreadable file NEVER aborts the scan; it
    degrades to a counted drop and the run continues.
  * Filenames are hashed to opaque ids before reaching an Event, and the
    session key is the path RELATIVE TO THE ROOT (not the bare stem), so two
    same-named files in different directories stay distinct threads.
  * `delta_prev_s` is censored (None) whenever the previous event was on a
    different day — a cross-midnight delta would let an analyzer pin the clock
    hour, which the wall forbids. Within-day tempo survives.
  * Naive timestamps (no offset) are read as UTC explicitly, so the same
    corpus yields identical deltas on any machine (never the host timezone).
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

# CODE_REF: require CODE-ADJACENT context, not bare English words. Every
# alternative needs a code shape (a call, a dotted call, a fence, a source
# file, a traceback frame, a CamelCase Error/Exception, a real def/import).
# Case-sensitive on the keyword/Error branches so prose "exception"/"error"
# does not match.
CODE_REF = re.compile(
    r"\b[A-Za-z_]\w*\([^)]*\)"                 # a call: foo(...)
    r"|\b[A-Za-z_]\w*\.[A-Za-z_]\w*\("          # method call: obj.method(
    r"|`[^`]+`|```"                              # inline / fenced code
    r"|\b\w+\.(py|js|ts|rs|go|rb|java|sql|sh)\b"  # source file
    r"|Traceback \(most recent call last\)"
    r"|\bline\s+\d+,\s+in\b"                     # python traceback frame
    r"|\b\w+(Error|Exception)\b"                # ValueError, KeyError (needs prefix)
    r"|\breturn\s+\w+\("                         # return a call
    r"|\b(def|class|async def)\s+\w+\s*\("     # def/class with a param list
    r"|\bfrom\s+[\w.]+\s+import\b"              # from x import y
    r"|\bimport\s+[a-z]\w*\.\w",                # import a.b (dotted module)
)
# AUTHORED: pasted code. Fenced, real def/class/decl lines, control flow ending
# in a colon, imports, a code-shaped assignment (RHS is a bracket/quote/call —
# NOT a bare number+unit), SQL, or a few language tells. Case-sensitive so
# prose "If you're ready:" (capital I) and "Select from the menu" don't match.
AUTHORED = re.compile(
    r"```"
    r"|^\s*(def|class|async\s+def)\s+\w+\s*\("
    r"|^\s*(for|while|if|elif|with|try|except)\b[^\n]*[):]\s*$"
    r"|^\s*(public|private|protected|static|func|fn|const|let|var)\s+\w"
    r"|^\s*(import\s+[\w.]+|from\s+[\w.]+\s+import)\b"
    r"|^\s*[A-Za-z_]\w*\s*=\s*([\[{('\"]|[A-Za-z_]\w*\()"
    r"|^\s*[A-Za-z_]\w*\([^)]*\)\s*$"           # a line that is just a call: print(x)
    r"|\b(SELECT|INSERT|UPDATE|DELETE)\b[^\n]*\b(FROM|INTO|SET|WHERE|VALUES)\b"
    r"|console\.log\(|println!\(|System\.out\.",
    re.M,
)
DELIB = re.compile(
    r"\btalk (to me )?about\b|let'?s (talk|discuss|explore)|\bdiscuss\b|pros?\s*(and|/|\-)\s*cons?"
    r"|trade.?offs?|think (through|about)\b|what do you think"
    r"|\byour thoughts\b|\bany thoughts\b|thoughts on\b|thoughts\?"
    r"|help me (think|understand|decide|figure|weigh)|walk me through"
    r"|weigh (the |our |my )?options\b|what (are|were) (the |my |our )?options|\b(the|my|our) options\b"
    r"|brainstorm|i'?m (thinking|wondering|considering)|convince me|push back", re.I)
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
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:                       # naive -> read as UTC, not host tz
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        epoch = dt.timestamp()
    except Exception:
        pass
    return d, epoch


def _iter_lines(f: Path):
    """Yield (line_index, parsed_or_None). An unreadable file yields one
    sentinel so the caller can count it as a drop and move on — never crash."""
    try:
        with f.open(encoding="utf-8-sig", errors="replace") as fh:
            for i, ln in enumerate(fh):
                if not ln.strip():
                    continue
                try:
                    yield i, json.loads(ln)
                except Exception:
                    yield i, None
    except OSError:
        yield -1, None


@register("claude-code")
def ingest(path: str, corpus_id: str = "corpus"):
    root = Path(path)
    raw = []          # (date, epoch|None, session_key, role, text, real_ref)
    dropped = 0
    for f in sorted(root.rglob("*.jsonl")):
        rel = f.relative_to(root).as_posix()
        for i, o in _iter_lines(f):
            if not isinstance(o, dict):
                dropped += 1
                continue
            if o.get("type") not in ("user", "assistant"):
                dropped += 1
                continue
            d, epoch = _parse_ts(o.get("timestamp"))
            if d is None:
                dropped += 1
                continue
            msg = o.get("message")
            if not isinstance(msg, dict):
                msg = {}
            content = msg.get("content")
            if isinstance(content, list):
                text = " ".join(b.get("text") or "" for b in content
                                if isinstance(b, dict) and b.get("type") == "text")
            else:
                text = content if isinstance(content, str) else ""
            raw.append((d, epoch, rel, o["type"], text, f"{rel}:{i+1}"))

    if not raw:
        return [], Quarantine(), dropped

    base = min(r[0] for r in raw)
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
        prev_day = None
        for d, epoch, _, role, text, real_ref in recs:
            day_offset = (d - base).days
            if role == "user":
                text, stripped = authored_text(text)
                author, dtype = AuthorClass.OPERATOR, DataType.PROMPT
            else:
                author, dtype, stripped = AuthorClass.MACHINE, DataType.RESPONSE, False
            if not text.strip():
                dropped += 1
                if epoch is not None:               # keep the clock advancing
                    prev_epoch, prev_day = epoch, day_offset
                continue
            # censor cross-day deltas: a midnight-crossing gap would pin the hour
            same_day = (prev_day == day_offset)
            delta = (epoch - prev_epoch) if (epoch is not None and prev_epoch is not None
                                             and same_day) else None
            if epoch is not None:
                prev_epoch, prev_day = epoch, day_offset
            opaque = _hash(sid, real_ref)
            ref_map[opaque] = real_ref
            events.append(Event(
                event_id=opaque, corpus_id=corpus_id, adapter_id="claude-code/1",
                source_ref=opaque, thread_id=sid, surface=Surface.CLI,
                author_class=author, data_type=dtype,
                time=CoarseTime(day_offset=day_offset, delta_prev_s=delta),
                features=_features(text, stripped)))
    return events, Quarantine(base_date_iso=base.isoformat(), ref_map=ref_map), dropped
