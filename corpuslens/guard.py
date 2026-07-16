"""corpuslens.guard — THE WALL.

Sits between ingestion and analysis. Four mechanisms in the spine:

  1. Quarantine custody: the calendar anchor, timezone, and the filename->line
     map are held privately by the Guard; `release()` is the supported door
     and it fail-closes on every path.
  2. Capability profile: the default profile grants NOTHING. Absolute calendar
     position, timezone, and person-shaped claims are all off by default.
  3. Claim gate: an analyzer whose declared claims are not on the process
     allowlist does not register. Unknown claim -> refusal (fail closed).
  4. Audit: every run produces a plain-language record of what ran, what was
     granted, and what was denied — a sentence a family can read.

WHAT THE WALL GUARANTEES, STATED HONESTLY (corrected after review). The wall
keeps the ABSOLUTE ANCHOR — which real date is day 0, which timezone, which
clock hour, and the raw filenames (which embed both) — out of the data an
analyzer receives. Recovering a real calendar date, weekday label, or hour
requires re-supplying the anchor through this Guard, with a capability + owner
token + logged justification.

WHAT IT DOES NOT DO, ALSO STATED HONESTLY:
  * It does not hide weekly *cadence*. `day_offset % 7` preserves the shape of
    a week up to one unknown rotation; that is inherent to relative-day data
    and cannot be walled off while still computing resumption/concurrency.
  * It does not fully hide *within-day time-of-day*. Cross-midnight deltas are
    censored (so the clock cannot be pinned at a day boundary), but the deltas
    within a single day survive for tempo analysis, and their cumulative span
    loosely BOUNDS the local time-of-day on a day one thread spans for many
    hours (e.g. a 21-hour span forces the first event before ~03:00 local).
    This is a weak local-clock bound — never the timezone, never the date —
    and we disclose it rather than claim an absolute "no clock hour" wall.
  * It is not an adversarial sandbox against the machine's OWNER. This is a
    local tool you run on your own logs to study yourself; a determined owner
    can always read their own quarantined data by editing their own script.
    The wall's job is to stop ACCIDENTAL leaks and to constrain analyzer
    PLUGINS — the default, supported path emits process only. Claiming it
    stops the owner would itself be the overclaim this project forbids.

If a *plugin analyzer running the supported path* can recover the absolute
anchor, that is a bug of the highest class: report it like one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .model import PERSON_CLAIM_TYPES, PROCESS_CLAIM_TYPES, Quarantine


class WallError(Exception):
    """A hard stop at the wall. Never swallowed."""


@dataclass(frozen=True)
class Profile:
    """Capabilities granted for a run. Default: nothing."""
    name: str = "default"
    capabilities: frozenset = frozenset()
    owner_token: Optional[str] = None   # required for any person-class release

    def grants(self, cap: str) -> bool:
        return cap in self.capabilities


DEFAULT_PROFILE = Profile()

# Capabilities that exist in the spine. Adding one is a design act.
KNOWN_CAPABILITIES = frozenset({
    "calendar_time",     # release the base date (turns day_offset into dates)
    "local_tz",          # release the timezone
    "person_inference",  # allow PERSON_CLAIM_TYPES analyzers to register
})


@dataclass
class AuditRecord:
    profile: str
    granted: list = field(default_factory=list)
    denied: list = field(default_factory=list)
    analyzers_run: list = field(default_factory=list)
    analyzers_refused: list = field(default_factory=list)
    n_events: int = 0
    n_dropped: int = 0

    def sentence(self) -> str:
        g = ", ".join(self.granted) or "nothing beyond process analysis"
        r = f"; refused: {', '.join(self.analyzers_refused)}" if self.analyzers_refused else ""
        base = (f"This run read {self.n_events} events (dropped {self.n_dropped}, counted not hidden), "
                f"ran {len(self.analyzers_run)} process analyzers under profile '{self.profile}', "
                f"and was granted {g}{r}. ")
        if self.granted:
            # a capability was released this run — do NOT claim nothing left the wall
            tail = ("Because the capability(ies) named above were granted, the corresponding "
                    "quarantined value(s) — calendar anchor, timezone, and/or filename — WERE "
                    "released under owner grant: this run is not anchor-free. Relative day and "
                    "within-day tempo also left the wall.")
        else:
            tail = ("No absolute calendar date, timezone, or filename left the wall; relative day "
                    "and within-day tempo did — these preserve weekly cadence, and on a day a single "
                    "thread spans for many hours they loosely bound the local time-of-day (never the "
                    "timezone or the date).")
        return base + tail


class Guard:
    """Holds the Quarantine privately (name-mangled) so the supported way to
    reach an anchored value is `release()`. This makes accidental access loud;
    it is not, and does not claim to be, unbypassable by the owner."""

    def __init__(self, quarantine: Quarantine, profile: Profile = DEFAULT_PROFILE):
        self.__q = quarantine          # name-mangled: not a casual public field
        self.profile = profile
        self.audit = AuditRecord(profile=profile.name)

    # ── quarantine custody ───────────────────────────────────────────────
    def release(self, cap: str, justification: str) -> object:
        """The supported door to quarantined values. Fail-closed on every path:
        unknown capability, ungranted capability, missing justification,
        or an anchor release without an owner token."""
        if cap not in KNOWN_CAPABILITIES:
            self.audit.denied.append(cap)
            raise WallError(f"unknown capability {cap!r} — absence of policy is denial")
        if not justification or not justification.strip():
            self.audit.denied.append(cap)
            raise WallError(f"capability {cap!r} requires a logged justification")
        if not self.profile.grants(cap):
            self.audit.denied.append(cap)
            raise WallError(f"capability {cap!r} not granted by profile {self.profile.name!r}")
        if cap in ("calendar_time", "local_tz") and self.profile.owner_token is None:
            self.audit.denied.append(cap)
            raise WallError(f"capability {cap!r} requires an owner token — a name is not an identity")
        self.audit.granted.append(f"{cap} ({justification.strip()})")
        if cap == "calendar_time":
            return self.__q.base_date_iso
        if cap == "local_tz":
            return self.__q.local_tz
        return True

    def resolve_ref(self, opaque_ref: str, justification: str) -> str:
        """Re-derive a real 'filename:line' from an Event's opaque source_ref —
        gated exactly like calendar_time, because filenames embed dates/names."""
        val = self.release("calendar_time", f"resolve_ref: {justification}")  # noqa: F841
        return self.__q.ref_map.get(opaque_ref, "")

    def n_events(self) -> int:
        return self.audit.n_events

    # ── claim gate ───────────────────────────────────────────────────────
    def admit(self, analyzer) -> bool:
        """True iff every claim the analyzer declares is representable under
        this profile. Person claims need `person_inference` AND an owner
        token; unknown claims are refused outright."""
        for claim in analyzer.claims:
            if claim in PROCESS_CLAIM_TYPES:
                continue
            if claim in PERSON_CLAIM_TYPES:
                if self.profile.grants("person_inference") and self.profile.owner_token:
                    continue
                self.audit.analyzers_refused.append(f"{analyzer.name} (person claim {claim!r})")
                return False
            self.audit.analyzers_refused.append(f"{analyzer.name} (unknown claim {claim!r})")
            return False
        return True
