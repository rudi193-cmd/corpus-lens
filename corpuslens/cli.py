"""corpuslens CLI — `python -m corpuslens run <path> --adapter claude-code`.

Runs under the DEFAULT profile: no calendar, no timezone, no person claims.
There is deliberately no CLI flag to grant capabilities — a grant is an
owner-side code change (a Profile constructed in your own script), not a
switch someone can flip in a command line they found in a README.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ingest
from .analyze import all_analyzers
from .guard import DEFAULT_PROFILE, Guard, WallError
from .render import markdown


def run(path: str, adapter: str, out: str | None) -> int:
    p = Path(path)
    if not p.exists():
        print(f"error: path does not exist: {path}", file=sys.stderr)
        return 2
    if not p.is_dir():
        print(f"error: expected a directory of *.jsonl session files, got a file: {path}\n"
              f"       point corpuslens at the parent directory, not a single session file.",
              file=sys.stderr)
        return 2

    n_files = sum(1 for f in p.rglob("*.jsonl") if f.is_file())
    events, quarantine, dropped = ingest.get(adapter)(path)
    guard = Guard(quarantine, DEFAULT_PROFILE)
    guard.audit.n_events = len(events)
    guard.audit.n_dropped = dropped
    if not events:
        if n_files == 0:
            print(f"error: no *.jsonl files found under {path}. Wrong directory?", file=sys.stderr)
        else:
            print(f"error: {n_files} *.jsonl file(s) under {path} but none yielded a datable, "
                  f"non-empty turn for adapter '{adapter}' (dropped {dropped}). Wrong adapter?",
                  file=sys.stderr)
        return 1

    results = {}
    for a in all_analyzers():
        if not guard.admit(a):
            continue
        results[a.name] = {"denominator": a.denominator, **a.run(events)}
        guard.audit.analyzers_run.append(a.name)
    report = markdown(results, guard.audit)
    try:
        report = guard.scan_egress(report)   # fail-closed backstop at the output door
    except WallError as e:
        # A quarantined value reached the rendered report. Do NOT emit it —
        # refuse loudly. The report is discarded, not printed.
        print(f"error: {e}", file=sys.stderr)
        return 3
    if out:
        try:
            with open(out, "w", encoding="utf-8") as f:
                f.write(report)
        except OSError as e:
            print(f"error: could not write --out {out}: {e}", file=sys.stderr)
            return 2
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
