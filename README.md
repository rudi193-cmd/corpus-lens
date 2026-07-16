# corpuslens

A local-first lens for your own human+agent corpus. Point it at your session
logs; get a process report — where your intent arrives, who writes the code,
whether you deliberate on purpose, what shape your threads have — with
reference points to grade yourself against.

**Stdlib only. Local only. Owner == subject.** Nothing to install beyond
Python, nothing leaves your machine, and this is for studying *yourself*.
Pointing it at another person (a child, a partner, an employee) is a different
consent object and is out of scope by design.

The rubric this instruments: [GRADING.md](https://github.com/rudi193-cmd/willow-seed/blob/main/GRADING.md)
(ten questions to grade your own system).

## The wall (why this is safe to hold)

The load-bearing design decision, inherited from the instrument's origin:
**relative time is process; absolute wall-clock position is person.** A
custody schedule was once reconstructed from keystroke timing alone — content
redaction does not scrub the shape of a week. So:

- Events carry **day offsets and deltas only**. The calendar anchor and
  timezone are quarantined at ingest; under the default profile there is no
  path from an analyzer back to a weekday or an hour. Un-assemblable, not
  refused.
- Analyzers declare **claim types** against a process-only allowlist.
  "He is [category]" has no representable claim type.
- Every gate **fails closed**: unknown capability, missing justification,
  absent owner token — all read as denial.
- Every run emits a **plain-language audit sentence** a family could read.
- There is deliberately **no CLI flag to grant capabilities** — a grant is an
  owner-side code change, not a switch in a README.

`tests/test_wall.py` red-teams all of this; the custody-shaped analysis is the
acceptance test — it must be unreachable.

## Quickstart

```bash
python3 -m corpuslens run ~/.claude/projects --adapter claude-code --out report.md
python3 -m corpuslens run ./my-cursor-sessions --adapter cursor
```

The battery (v0): `steering_density`, `thread_shape`, `composition_mix`,
`clarification_pull` — each with a named denominator, dropped-event counts
reported (never hidden), and reference points from one measured N=1 operator
corpus plus WildChat/OASST population aggregates.

## Honesty about the numbers

The classifiers are regex heuristics: trust direction plus your own
spot-check, never raw percentages. The reference N=1 was verified by
re-derivation from raw and corrected five times in one session — the
reference table inherits those corrections, not the first drafts.

## Status: spine (v0.1)

Built: event model, the wall, two adapters (claude-code, cursor), injection
filter, four analyzers, markdown renderer, CLI, 13 tests.

Named and deliberately unbuilt:
- `distinctive_tokens` and any content-derived token feature — **absent until
  the feature layer has its own PII scrub** (that feature is where names and
  identities live).
- The guardian-consent model (owner ≠ subject) — the biggest gap between this
  toolkit and any family-facing instrument; not solved, so not shipped.
- Bootstrap CIs / band-sensitivity on rates; claude.ai web-export and
  agent-fleet adapters; JSON/prose renderers.
- The cursor adapter keeps only turns carrying the runtime's injected
  timestamp tag — conservative, undercounts, reported in the audit line.

Lineage: consolidates the ad-hoc instruments of the willow personal-research
sessions (2026-07) into the architecture planned there; the inference wall is
the `learner-model-ground-rules` made mechanical.

Apache-2.0 · ΔΣ = 42
