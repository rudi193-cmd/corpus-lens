"""corpuslens.guard — THE WALL.

Sits between ingestion and analysis. Four mechanisms in the spine:

  1. Quarantine custody: the calendar anchor and timezone never reach an
     analyzer; `Guard.release()` is the only door and it fail-closes.
  2. Capability profile: the default profile grants NOTHING. Person-shaped
     analysis is un-assemblable by default, not merely refused.
  3. Claim gate: an analyzer whose declared claims are not on the process
     allowlist does not register. Unknown claim -> refusal (fail closed).
  4. Audit: every run produces a plain-language record of what ran, what was
     granted, and what was denied — a sentence a family can read.

Surveillance-shaped analysis is meant to be structurally unreachable here,
not discouraged. If you find a way through the wall, that is a bug of the
highest class: report it like one.
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
        return (f"This run read {self.n_events} events (dropped {self.n_dropped}, reported not hidden), "
                f"ran {len(self.analyzers_run)} process analyzers under profile '{self.profile}', "
                f"and was granted {g}{r}. No content and no calendar position left the wall.")


class Guard:
    def __init__(self, quarantine: Quarantine, profile: Profile = DEFAULT_PROFILE):
        self._q = quarantine
        self.profile = profile
        self.audit = AuditRecord(profile=profile.name)

    # ── quarantine custody ───────────────────────────────────────────────
    def release(self, cap: str, justification: str) -> object:
        """The only door to quarantined values. Fail-closed on every path:
        unknown capability, ungranted capability, missing justification,
        or a person-class release without an owner token."""
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
            return self._q.base_date_iso
        if cap == "local_tz":
            return self._q.local_tz
        return True

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
