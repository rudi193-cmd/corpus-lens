"""Markdown rendering: the report plus the audit sentence, always together —
a result without its audit record is not a corpuslens result."""
from __future__ import annotations

import json


def markdown(results: dict, audit) -> str:
    out = ["# corpuslens report", ""]
    out.append(f"> {audit.sentence()}")
    out.append("")
    for name, res in results.items():
        out.append(f"## {name}")
        out.append("```json")
        out.append(json.dumps(res, indent=2, default=str))
        out.append("```")
        out.append("")
    out.append("*Numbers are heuristics plus your own eyes: spot-check before you cite. "
               "Reference points are one measured N=1 plus public population aggregates.*")
    return "\n".join(out)
