# Security policy

corpuslens has one safety-critical surface: **the inference wall**. Its job is to
keep the absolute time anchor, timezone, and raw filenames out of the data an
analyzer sees, so that process analysis cannot be turned into surveillance of a
person's calendar life.

## What counts as a wall breach (report these)

Under the **default profile**, a plugin analyzer running the supported path
receives only the list of `Event`s. If, from that alone, you can recover any of:

- the absolute **calendar date** of an event,
- a real **weekday label** (e.g. "this happened on a Tuesday"),
- the **clock time-of-day** *more tightly* than the disclosed loose bound, or
- the **timezone**,

that is a security issue of the highest class — the exact thing the wall exists
to prevent. Please report it privately (see below) rather than opening a public
issue, and include the analyzer code that performs the recovery.

## What is NOT a breach (disclosed limits, by design)

These are documented in the README and `guard.py` and are **not** bugs:

- **Weekly cadence** is reconstructable (`day_offset % 7` up to an unknown
  rotation) — Mon-vs-weekend rhythm is visible; which real weekday is not.
- **A loose within-day time-of-day bound** survives on a day one thread spans
  for many hours (within-day tempo is kept for analysis). This bounds, never
  pins, the local clock — and never the date or timezone.
- **The owner can read their own quarantined data** by editing their own script.
  The wall stops accidental leaks and constrains plugins; it is not, and does not
  claim to be, an adversarial sandbox against the machine's owner.

If your finding matches one of these, it is already disclosed — but if the docs
describe it inaccurately, a documentation PR is very welcome.

## Reporting

Use GitHub's private vulnerability reporting on this repository ("Security" →
"Report a vulnerability"), or open a minimal issue asking for a private channel
without disclosing the details. Please give the maintainer a reasonable window to
respond before public disclosure.

There is no bounty; this is a small give-back project. What you get is a fast,
grateful fix and credit in the changelog if you'd like it.
