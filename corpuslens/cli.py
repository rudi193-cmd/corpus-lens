"""corpuslens CLI — `python -m corpuslens run <path> --adapter claude-code`.

Runs under the DEFAULT profile: no calendar, no timezone, no person claims.
There is deliberately no CLI flag to grant capabilities — a grant is an
owner-side code change (a Profile constructed in your own script), not a
switch someone can flip in a command line they found in a README.
"""
from __future__ import annotations

import argparse
import sys

from . import ingest
from .analyze import all_analyzers
from .guard import DEFAULT_PROFILE, Guard
from .render import markdown


def run(path: str, adapter: str, out: str | None) -> int:
    events, quarantine, dropped = ingest.get(adapter)(path)
    guard = Guard(quarantine, DEFAULT_PROFILE)
    guard.audit.n_events = len(events)
    guard.audit.n_dropped = dropped
    results = {}
    for a in all_analyzers():
        if not guard.admit(a):
            continue
        results[a.name] = {"denominator": a.denominator, **a.run(events)}
        guard.audit.analyzers_run.append(a.name)
    report = markdown(results, guard.audit)
    if out:
        with open(out, "w") as f:
            f.write(report)
        print(f"wrote {out}")
    else:
        print(report)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="corpuslens")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the process battery on a corpus directory")
    r.add_argument("path")
    r.add_argument("--adapter", required=True, choices=ingest.available())
    r.add_argument("--out", default=None)
    args = p.parse_args(argv)
    if args.cmd == "run":
        return run(args.path, args.adapter, args.out)
    return 2


if __name__ == "__main__":
    sys.exit(main())
