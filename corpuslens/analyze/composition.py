"""Who writes the code, and do you deliberate on purpose?
(GRADING.md questions 2–3.) Feature-based; content never reaches here."""
from __future__ import annotations

import statistics

from ..model import AuthorClass, DataType
from . import register

REFERENCE = {
    "wildchat_coding_population": {"authored_pct": 14.5, "read_ref_pct": 36.0, "delib_pct": 3.2},
    "wildchat_all": {"authored_pct": 3.0, "read_ref_pct": 12.3, "delib_pct": 6.6},
    "oasst_general_chat": {"delib_pct": 7.3},
    "measured_director_n1": {"authored_pct": 6.3, "read_ref_pct": 18.3, "delib_pct": 5.2},
}


@register("composition_mix", claims=("composition_mix",),
          denominator="operator prompt turns with >=12 characters (de-injected)")
def composition_mix(events):
    turns = [e.features for e in events
             if e.author_class is AuthorClass.OPERATOR and e.data_type is DataType.PROMPT
             and e.features.get("char_count", 0) >= 12]
    n = len(turns)
    if not n:
        return {"error": "no operator prompts found"}
    pct = lambda k: round(100 * sum(1 for f in turns if f.get(k)) / n, 1)
    return {
        "n_turns": n,
        "authored_code_pct": pct("code_authored"),
        "code_ref_pct": pct("code_ref"),
        "delib_pct": pct("delib"),
        "median_words": statistics.median(f["word_count"] for f in turns),
        "reference": REFERENCE,
        "reading": ("above the coding population on authored/read-ref = you bring the code to the "
                    "machine; well below it = the machine holds the code and you direct. "
                    "delib above your domain population = you summon the teaching surface on purpose."),
    }


@register("clarification_pull", claims=("clarification_pull",),
          denominator="machine response turns (>=12 chars)")
def clarification_pull(events):
    ordered = {}
    for e in events:
        ordered.setdefault(e.thread_id, []).append(e)
    asst = forks = 0
    for turns in ordered.values():
        for i, e in enumerate(turns):
            if not (e.author_class is AuthorClass.MACHINE and e.data_type is DataType.RESPONSE):
                continue
            if e.features.get("char_count", 0) < 12:
                continue
            asst += 1
            if e.features.get("clarify") and e.features.get("question"):
                # a fork = the NEXT operator turn in the thread answers, even if
                # machine tool-result turns sit between (review fix — strict
                # adjacency missed forks whenever the assistant used a tool).
                nxt = next((turns[j] for j in range(i + 1, len(turns))
                            if turns[j].author_class is AuthorClass.OPERATOR), None)
                if nxt is not None:
                    forks += 1
    if not asst:
        return {"error": "no machine responses in corpus (prompt-only adapter?)"}
    return {"assistant_turns": asst, "clarification_forks_pct": round(100 * forks / asst, 2),
            "reference": {"measured_cli": 3.4, "measured_cursor": 2.47}}
