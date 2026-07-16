"""Adapter: Claude Code session JSONL (one file per session, `timestamp` log
field per event line, `message.content` blocks). Point it at a directory; it
walks `**/*.jsonl`.

Provenance rule (non-negotiable, earned the hard way): dates come from the
`timestamp` LOG FIELD only — never from date-strings inside content. Content
dates once inflated a resumption count 10x.
"""
from __future__ import annotations

import datetime
import json
import re
import statistics
from pathlib import Path

from ..model import AuthorClass, CoarseTime, DataType, Event, Quarantine, Surface
from . import register
from .injection import authored_text

ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T")

CODE_REF = re.compile(
    r"\bline\s+\d+\b|\breturns?\b|\bTraceback\b|Error\b|\b\w+\(\)|\b\w+\.\w+\(|\.py\b"
    r"|\bdef\b|\bimport\b|\bfunction\b|\bmethod\b|\bvariable\b|\bmodule\b", re.I)
AUTHORED = re.compile(r"^\s{4,}(def|class|for|if|return|import|while|try)\b", re.M)
DELIB = re.compile(
    r"\btalk (to me )?about\b|let'?s (talk|discuss|explore)|\bdiscuss\b|pros?\s*(and|/|\-)\s*cons?"
    r"|trade.?offs?|think (through|about)\b|what do you think|\bthoughts\b"
    r"|help me (think|understand|decide|figure|weigh)|walk me through|\boptions\b|brainstorm"
    r"|i'?m (thinking|wondering|considering)|convince me|push back", re.I)
CLARIFY = re.compile(
    r"do you (mean|want)|would you like|should i\b|which (one|of|do|would|approach)"
    r"|to clarify|can you confirm|just to confirm|one question|quick question", re.I)


def _features(text: str, stripped: bool) -> dict:
    return {
        "word_count": len(text.split()),
        "code_fenced": text.count("```") >= 2,
        "code_authored": bool(AUTHORED.search(text)) or text.count("```") >= 2,
        "code_ref": bool(CODE_REF.search(text)),
        "delib": bool(DELIB.search(text)),
        "question": "?" in text,
        "clarify": bool(CLARIFY.search(text)),
        "injected_stripped": stripped,
    }


def _date_of(line_obj: dict):
    ts = line_obj.get("timestamp")
    if isinstance(ts, str) and ISO.match(ts):
        return datetime.date(int(ts[:4]), int(ts[5:7]), int(ts[8:10])), ts
    return None, None


@register("claude-code")
def ingest(path: str, corpus_id: str = "corpus"):
    root = Path(path)
    raw_events = []   # (date, epoch_s|None, session, role, text, source_ref)
    dropped = 0
    for f in sorted(root.rglob("*.jsonl")):
        session = f.stem
        for i, ln in enumerate(f.open(errors="replace")):
            try:
                o = json.loads(ln)
            except Exception:
                dropped += 1
                continue
            if not isinstance(o, dict) or o.get("type") not in ("user", "assistant"):
                continue
            d, ts = _date_of(o)
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
            epoch = None
            try:
                epoch = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
            raw_events.append((d, epoch, session, o["type"], text, f"{f.name}:{i+1}"))

    if not raw_events:
        return [], Quarantine(), dropped

    base = min(e[0] for e in raw_events)          # calendar anchor — quarantined
    events = []
    prev_epoch: dict = {}
    for d, epoch, session, role, text, ref in raw_events:
        if role == "user":
            text, stripped = authored_text(text)
            author, dtype = AuthorClass.OPERATOR, DataType.PROMPT
        else:
            author, dtype, stripped = AuthorClass.MACHINE, DataType.RESPONSE, False
        if not text.strip():
            dropped += 1
            continue
        delta = None
        if epoch is not None and session in prev_epoch:
            delta = epoch - prev_epoch[session]
        if epoch is not None:
            prev_epoch[session] = epoch
        events.append(Event(
            event_id=f"{session}:{ref}", corpus_id=corpus_id, adapter_id="claude-code/1",
            source_ref=ref, thread_id=session, surface=Surface.CLI,
            author_class=author, data_type=dtype,
            time=CoarseTime(day_offset=(d - base).days, delta_prev_s=delta),
            features=_features(text, stripped)))
    return events, Quarantine(base_date_iso=base.isoformat()), dropped
