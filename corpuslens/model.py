"""corpuslens.model — the common event model and the types that ARE the wall.

The seam (from the design, 2026-07-14): relative time is process; absolute
wall-clock position is person. An Event therefore carries ONLY relative time
(day offset from corpus start, seconds since previous event in thread). The
absolute anchor needed to reconstruct a calendar is quarantined at ingest and
held by the Guard — analyzers cannot reach it without a granted capability.

Content is read once at ingest to derive process features; the Event does not
carry content. NOTE (review note 1, 2026-07-14): `distinctive_tokens` is
deliberately ABSENT from the feature set — that feature is exactly where
names and identities live, and it must not exist until the feature layer has
its own PII scrub. Absence is the current scrub.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Surface(str, Enum):
    CLI = "cli"
    WEB = "web"
    IDE = "ide"
    FLEET = "fleet"


class AuthorClass(str, Enum):
    OPERATOR = "operator"
    MACHINE = "machine"
    AGENT = "agent"


class DataType(str, Enum):
    PROMPT = "prompt"
    RESPONSE = "response"
    TOOL_EVENT = "tool_event"
    META = "meta"


# ── claim ontology ───────────────────────────────────────────────────────────
# Analyzers must declare what KIND of statement they emit. Only process-shaped
# claims are representable; "he is [category]" has no claim type, so it cannot
# be output. Adding a person-shaped claim type is a deliberate, reviewable act.
PROCESS_CLAIM_TYPES = frozenset({
    "steering_density",       # where intent arrives (upfront vs mid-task)
    "composition_mix",        # authored / read-ref / deliberation shares
    "thread_shape",           # threads, resumptions, concurrency (relative days)
    "tempo",                  # inter-event durations
    "clarification_pull",     # fork/deferral rates
    "turns_to_completion",
    "leakage_demonstration",  # quarantined class: proves a leak, never ships data
})

PERSON_CLAIM_TYPES = frozenset({
    # Representable ONLY inside the quarantined demonstration class; no analyzer
    # in the default registry may declare these.
    "life_partition",         # weekday x hour maps, custody-shaped inference
})


@dataclass(frozen=True)
class CoarseTime:
    """Relative position only. day_offset counts from the corpus's first event;
    there is no path from this object back to a calendar."""
    day_offset: int
    delta_prev_s: Optional[float] = None  # fine RELATIVE time is process-safe


@dataclass
class Event:
    event_id: str
    corpus_id: str
    adapter_id: str
    source_ref: str            # file:line — the re-derivation anchor
    thread_id: str
    surface: Surface
    author_class: AuthorClass
    data_type: DataType
    time: CoarseTime
    features: dict = field(default_factory=dict)
    # process features only: word_count, code_fenced, code_ref, delib,
    # question, clarify, injected_stripped. No content. No distinctive tokens.


@dataclass
class Quarantine:
    """What the adapter saw but the Event must not carry. Held by the Guard;
    released only capability-by-capability, with a logged justification."""
    base_date_iso: Optional[str] = None   # calendar anchor for day_offset 0
    local_tz: Optional[str] = None
