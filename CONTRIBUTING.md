# Contributing to corpuslens

Thanks for looking. corpuslens is a small, honest tool with a few load-bearing
rules. Contributions are welcome as long as they hold the rules — most of what
follows is about *what not to break*, because that is where this project's value
lives.

## The one rule: never overclaim

The docs, the docstrings, and the run's audit sentence must never promise more
than the code delivers — including claims about what the tool itself protects.
If you change what the code does, change the claim in the same PR. Two concrete
forms this takes:

- **The wall's claims must match the wall's code.** The README and `guard.py`
  say exactly what does and does not leave the wall (the absolute date, weekday
  label, timezone, and filenames are kept out; weekly cadence and a loose
  within-day time-of-day bound are *disclosed as not hidden*). If you add a field
  to `Event` or change the timing channel, re-audit those claims and the audit
  sentence in `guard.py`.
- **Classifiers undercount rather than overclaim.** The regex classifiers
  (`CODE_REF`, `AUTHORED`, `DELIB`, `CLARIFY`) feed headline percentages. When
  they are wrong, they must be wrong in the *under*-counting direction — a false
  negative on real code is acceptable; a false positive on ordinary prose that
  inflates "you write code" is not. Add prose fixtures for any classifier change.

## The wall discipline (for new adapters and analyzers)

- **A new adapter** must never put an absolute calendar date, timezone, or raw
  filename on an `Event`. Dates become relative `day_offset`s from the corpus
  start; the calendar anchor and the real `filename:line` go into the
  `Quarantine` (reachable only through the `Guard`); session/thread ids are
  opaque hashes of the path relative to the root. Count every skipped line
  toward `dropped` — nothing silently discarded — and never let one malformed
  line or unreadable file crash the run.
- **A new analyzer** must declare a `claim` type on the process-only allowlist
  in `model.py` (a person-shaped claim like `life_partition` stays behind the
  capability gate and out of the default registry) and a **named denominator**
  that matches its actual filter. Analyzers receive only the `Event` list —
  relative time and process features, never content.

If you find a way for a default-profile analyzer to recover the absolute anchor
via the supported path, that is a security issue, not a feature request — see
[SECURITY.md](SECURITY.md).

## Reference numbers are verified from raw

The reference points in the analyzers (the measured N=1, the WildChat/OASST
aggregates) were derived from raw sources and re-verified. If you change a
reference number, say where it came from and how it was checked — never adjust a
reference to make a result look better.

## Running the tests

```bash
python -m unittest discover -s tests -v
python -W error::ResourceWarning -m unittest discover -s tests   # no leaked handles
```

Every fixed bug gets a regression test; the wall tests (`tests/test_wall.py`)
are the acceptance tests for the centerpiece — including one that *documents*
what the wall does NOT hide, so nobody silently re-introduces an overclaim. CI
runs the suite on Python 3.10–3.13 plus a packaging smoke test.

## Scope

corpuslens is **owner == subject**: a tool you run on your own logs to study
yourself. Pointing it at another person is a different consent object and is out
of scope by design; the guardian-consent model is deliberately unbuilt. PRs that
add person-targeting analysis will be declined on those grounds, not on quality.

## How we work here

Plainly and honestly. Disagreement is welcome; a PR that makes the tool claim
*less* is usually more valuable than one that makes it claim more. Be kind, be
specific, and when you are not sure, say so.
