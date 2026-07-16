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

## The wall (what it guarantees, stated honestly)

The load-bearing design decision, inherited from the instrument's origin:
**relative time is process; the absolute anchor is person.** A custody
schedule was once reconstructed from keystroke timing alone — content
redaction does not scrub the shape of a week. So:

- Events carry **relative day offsets and deltas only**. The calendar anchor
  (which real date is day 0), the timezone, and the raw filenames (which embed
  dates and names) are quarantined at ingest and released only through the
  Guard with a granted capability + owner token + logged justification, fail-
  closed on every path.
- Analyzers declare **claim types** against a process-only allowlist.
  "He is [category]" has no representable claim type.
- Every run emits a **plain-language audit sentence** naming exactly what left
  the wall, and there is deliberately **no CLI flag to grant capabilities** —
  a grant is an owner-side code change.

**What this does — and does not — guarantee (read this).** The wall keeps the
*absolute anchor* out of the analysis: a real calendar **date**, a real
**weekday label**, and the **timezone** cannot be recovered without
re-supplying, through the Guard, the anchor you alone hold. What the wall does
**not** do:

- It does **not hide weekly cadence.** Relative day offsets preserve the shape
  of a week (`day_offset % 7` up to one unknown rotation) — that is inherent to
  computing resumption and concurrency at all, and we do not pretend otherwise.
  Mon-vs-weekend rhythm is visible; *which* real weekday is not.
- It does **not fully hide within-day time-of-day.** Cross-midnight deltas are
  censored, so the clock can't be pinned at a day boundary — but within-day
  tempo deltas survive (a tempo signal is the point), and their cumulative
  span loosely *bounds* the local time-of-day on a day one thread runs for many
  hours (a 21-hour span puts the first event before ~03:00 local). This is a
  weak local-clock **bound** — never the timezone, never the date. We disclose
  it rather than claim an absolute "no clock hour."
- It is **not an adversarial sandbox against you, the owner.** This is a local
  tool you run on your own logs to study yourself; you can always read your own
  quarantined data by editing your own script. The wall stops *accidental*
  leaks and constrains analyzer *plugins* — the supported path emits process
  only. Claiming it could stop its own owner would be the overclaim this
  project is built to forbid.

`tests/test_wall.py` holds the wall to exactly these claims — including a test
that asserts a plugin *cannot* recover the absolute anchor via the supported
path, and one that documents that weekly cadence *is* reconstructable.

## Install

Python 3.10+, no dependencies. Not on PyPI yet — install from source:

```bash
git clone https://github.com/rudi193-cmd/corpus-lens
cd corpus-lens
pip install .           # or: pip install -e .  (for development)
```

This installs a `corpuslens` console command. You can also run it without
installing, straight from a clone, via `python3 -m corpuslens`.

## Quickstart

```bash
corpuslens run ~/.claude/projects --adapter claude-code --out report.md
corpuslens run ./my-cursor-sessions --adapter cursor
# equivalently, from a clone without installing:
python3 -m corpuslens run ~/.claude/projects --adapter claude-code
```

Point `--adapter claude-code` at a directory of Claude Code session `.jsonl`
files, or `--adapter cursor` at a directory of Cursor session `.jsonl` files.
The report prints to stdout (or `--out FILE`), and always opens with a
plain-language audit line naming exactly what left the wall and how many input
lines were dropped.

The battery (v0): `steering_density`, `thread_shape`, `composition_mix`,
`clarification_pull` — each with a named denominator, dropped-event counts
reported (never hidden), and reference points from one measured N=1 operator
corpus plus WildChat/OASST population aggregates.

## Tests

```bash
python3 -m unittest discover -s tests
```

The suite covers the wall (fail-closed release, cross-midnight censoring, the
supported-path anchor-recovery attempt, the granted-profile audit sentence),
the adapters (drop-count accounting, malformed-line and unreadable-file
isolation, BOM, out-of-range dates, timezone reproducibility), and a
regression test for every fixed review finding.

## Honesty about the numbers

The classifiers are regex heuristics: trust direction plus your own
spot-check, never raw percentages. The reference N=1 was verified by
re-derivation from raw and corrected five times in one session — the
reference table inherits those corrections, not the first drafts.

## Status: spine (v0.1)

Built: event model, the wall, two adapters (claude-code, cursor), injection
filter, four analyzers, markdown renderer, CLI, test suite (wall + pipeline +
regression tests for every review finding).

Named and deliberately unbuilt:
- `distinctive_tokens` and any content-derived token feature — **absent until
  the feature layer has its own PII scrub** (that feature is where names and
  identities live).
- The guardian-consent model (owner ≠ subject) — the biggest gap between this
  toolkit and any family-facing instrument; not solved, so not shipped.
- Bootstrap CIs / band-sensitivity on rates; claude.ai web-export and
  agent-fleet adapters; JSON/prose renderers.
- The cursor adapter keeps only turns carrying the runtime's injected
  timestamp tag — conservative, undercounts, and **every dropped turn is
  counted in the audit line** (not silently discarded).

The classifiers are regex heuristics with known false-positive/negative modes
(a mixed personal + coding corpus is where they are weakest); the reference
numbers are one verified N=1, not a population you belong to. Grade direction,
spot-check before you cite.

Lineage: consolidates the ad-hoc instruments of the willow personal-research
sessions (2026-07) into the architecture planned there; the inference wall is
the `learner-model-ground-rules` made mechanical.

Apache-2.0 · ΔΣ = 42
