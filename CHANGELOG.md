# Changelog

All notable changes to corpuslens are recorded here. This project keeps to the
spirit of [Keep a Changelog](https://keepachangelog.com) and dated, in-the-open
amendments — corrections sit beside the record they correct, never overwrite it.

## [0.1.0] — unreleased (spine)

First cut: the wall, two adapters, four analyzers, hardened across four rounds
of adversarial review.

### Added
- **The inference wall** (`guard.py`, `model.py`): `Event`s carry relative time
  only (day offsets + within-day deltas, cross-midnight deltas censored); the
  calendar anchor, timezone, and real filenames are quarantined and released
  only through a fail-closed `Guard` (capability + owner token + logged
  justification). Analyzers declare claim types against a process-only
  allowlist. Every run emits a plain-language audit sentence naming exactly what
  left the wall — and disclosing what it does not hide (weekly cadence; a loose
  within-day time-of-day bound).
- **Adapters**: `claude-code` and `cursor` session JSONL, injection-filtered,
  dates from log fields only, filenames hashed to opaque ids, every dropped line
  counted, malformed-line and unreadable-file isolation, BOM-safe, timezone-
  reproducible.
- **Analyzers**: `steering_density`, `thread_shape`, `composition_mix`,
  `clarification_pull` — each with a named denominator and reference points from
  a measured N=1 plus public population aggregates.
- **CLI** (`corpuslens run … --adapter …`), markdown report, an annotated
  reproducible [example](examples/EXAMPLE.md), and a test suite whose wall tests
  double as the acceptance tests for the centerpiece.
- **Egress backstop** (`Guard.scan_egress`, wired at the CLI output door): a
  defense-in-depth re-check of the rendered report right before it leaves. The
  wall keeps the anchor out of `Event`s upstream; this catches the accidental
  leak that upstream guarantee is supposed to prevent — if a quarantined value
  (calendar anchor, timezone, or a real filename) whose capability was not
  released this run appears verbatim in the report, the emit is refused
  (fail-closed, exit code 3) and the report is discarded. Grant-aware (a value
  released under an owner grant is allowed to appear) and payload-free (the
  error never echoes the value it caught). Hostile fixtures in `test_wall.py`
  and an end-to-end leaking-analyzer test in `test_pipeline.py`.

### Deliberately not built (named, not hidden)
- Any content-derived token feature (`distinctive_tokens`) — absent until a
  feature-layer PII scrub exists.
- The guardian-consent model (owner ≠ subject) — out of scope by design.
- Bootstrap CIs, web-export / agent-fleet adapters, JSON/prose renderers.
