"""End-to-end + a regression test for every review finding that was fixed."""
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from corpuslens import ingest
from corpuslens.analyze import all_analyzers, register
from corpuslens.cli import main as cli_main
from corpuslens.guard import Guard
from corpuslens.ingest.claude_code import AUTHORED, CODE_REF
from corpuslens.render import markdown


def _cc_line(role, text, ts):
    return json.dumps({"type": role, "timestamp": ts,
                       "message": {"content": [{"type": "text", "text": text}]}})


def _write(path, lines, bom=False):
    data = "\n".join(lines) + "\n"
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8") as f:
        f.write(data)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        _write(self.d / "s1.jsonl", [
            _cc_line("user", "build the parser for the config file please", "2026-02-01T10:00:00Z"),
            _cc_line("assistant", "Done. Should I add validation, or keep it minimal?", "2026-02-01T10:05:00Z"),
            _cc_line("user", "it still fails on empty input, fix that", "2026-02-01T10:20:00Z"),
            _cc_line("user", "lets talk about options for the cache layer", "2026-02-03T09:00:00Z"),
        ])
        _write(self.d / "s2.jsonl", [
            _cc_line("user", "<system-reminder>x</system-reminder> what does mastery.py return on line 40?", "2026-02-02T08:00:00Z"),
            _cc_line("assistant", "It returns the posterior.", "2026-02-02T08:01:00Z"),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_ingest_strips_injection_and_quarantines(self):
        events, q, dropped = ingest.get("claude-code")(str(self.d))
        self.assertEqual(q.base_date_iso, "2026-02-01")
        self.assertTrue(all(e.time.day_offset in (0, 1, 2) for e in events))
        s2u = [e for e in events if e.author_class == "operator" and e.features["injected_stripped"]]
        self.assertTrue(s2u and s2u[0].features["code_ref"])

    def test_no_filename_reaches_events(self):
        events, q, _ = ingest.get("claude-code")(str(self.d))
        for e in events:
            for fld in (e.event_id, e.source_ref, e.thread_id):
                self.assertNotIn(".jsonl", fld)
                self.assertFalse(re.search(r"\d{4}-\d\d-\d\d", fld))
        # but the real ref survives in the quarantined map for gated re-derivation
        self.assertTrue(any(".jsonl" in v for v in q.ref_map.values()))

    def test_battery_runs_and_report_renders(self):
        events, q, dropped = ingest.get("claude-code")(str(self.d))
        guard = Guard(q); guard.audit.n_events = len(events); guard.audit.n_dropped = dropped
        results = {a.name: a.run(events) for a in all_analyzers() if guard.admit(a)}
        self.assertEqual(results["steering_density"]["sessions"], 2)
        self.assertEqual(results["thread_shape"]["threads"], 2)
        # s1 has a 2026-02-01 -> 02-03 gap = 2 days = one 2-6d resumption
        self.assertEqual(results["thread_shape"]["resumptions_2to6d"], 1)
        self.assertEqual(results["thread_shape"]["resumptions_ge14d"], 0)
        self.assertGreaterEqual(results["composition_mix"]["delib_pct"], 1)
        report = markdown(results, guard.audit)
        self.assertIn("No absolute calendar date", report)

    # ── regression tests, one per review finding ────────────────────────────

    def test_bom_does_not_eat_the_opener(self):
        b = Path(self.tmp.name) / "bom.jsonl"
        _write(b, [_cc_line("user", "first turn is the opener here", "2026-02-01T10:00:00Z"),
                   _cc_line("assistant", "reply", "2026-02-01T10:01:00Z")], bom=True)
        sub = tempfile.TemporaryDirectory()
        Path(sub.name, "bom.jsonl").write_bytes(b.read_bytes())
        events, q, dropped = ingest.get("claude-code")(sub.name)
        openers = [e for e in events if e.author_class == "operator"]
        self.assertTrue(openers and "opener" in "".join(str(e.features) for e in openers) or
                        any(e.features["word_count"] >= 5 for e in openers))
        self.assertEqual(dropped, 0)   # the BOM line is NOT dropped
        sub.cleanup()

    def test_nondict_and_system_lines_are_counted_dropped(self):
        j = Path(self.tmp.name) / "junk.jsonl"
        _write(j, ['[1,2,3]', '42', 'null', '{"type":"system","timestamp":"2026-02-01T10:00:00Z"}',
                   'not json at all',
                   _cc_line("user", "a real datable operator turn here", "2026-02-01T10:00:00Z")])
        sub = tempfile.TemporaryDirectory()
        Path(sub.name, "junk.jsonl").write_bytes(j.read_bytes())
        events, q, dropped = ingest.get("claude-code")(sub.name)
        self.assertEqual(len(events), 1)
        self.assertEqual(dropped, 5)   # every skipped line counted, none hidden
        sub.cleanup()

    def test_out_of_order_lines_give_no_negative_delta(self):
        o = Path(self.tmp.name) / "ooo.jsonl"
        _write(o, [_cc_line("user", "later turn appears first in the file", "2026-02-01T12:00:00Z"),
                   _cc_line("user", "earlier turn appears second in the file", "2026-02-01T09:00:00Z")])
        sub = tempfile.TemporaryDirectory()
        Path(sub.name, "ooo.jsonl").write_bytes(o.read_bytes())
        events, q, _ = ingest.get("claude-code")(sub.name)
        for e in events:
            if e.time.delta_prev_s is not None:
                self.assertGreaterEqual(e.time.delta_prev_s, 0)
        sub.cleanup()

    def test_code_ref_does_not_fire_on_plain_prose(self):
        prose = ["The company returns to profitability next quarter.",
                 "There was an Error in judgment when we hired that vendor.",
                 "As a function of time, sales decline in winter.",
                 "I import goods from overseas for my business."]
        for s in prose:
            self.assertFalse(CODE_REF.search(s), f"false positive on: {s}")
        for s in ["what does foo() return?", "see mastery.py line 40", "hit a ValueError"]:
            self.assertTrue(CODE_REF.search(s), f"false negative on: {s}")

    def test_authored_catches_unfenced_paste(self):
        self.assertTrue(AUTHORED.search("x = 1\nprint(x)"))
        self.assertTrue(AUTHORED.search("```\nx=1\n```"))
        self.assertFalse(AUTHORED.search("just talking about the plan for tomorrow"))

    def test_denominator_is_character_based(self):
        # a 5-char two-word turn must NOT count toward a ">=12 characters" denom
        short = Path(self.tmp.name) / "short.jsonl"
        _write(short, [_cc_line("user", "do it", "2026-02-01T10:00:00Z"),
                       _cc_line("user", "here is a much longer operator instruction", "2026-02-01T10:05:00Z")])
        sub = tempfile.TemporaryDirectory()
        Path(sub.name, "short.jsonl").write_bytes(short.read_bytes())
        events, q, _ = ingest.get("claude-code")(sub.name)
        from corpuslens.analyze.composition import composition_mix
        res = composition_mix(events)
        self.assertEqual(res["n_turns"], 1)   # "do it" (5 chars) excluded
        sub.cleanup()

    def test_cursor_counts_untagged_drops(self):
        c = Path(self.tmp.name) / "cur.jsonl"
        tagged = {"role": "user", "message": {"content": [{"type": "text",
                  "text": "<timestamp>Tuesday, May 19, 2026, 12:38 PM (UTC-6)</timestamp>\n<user_query>fix the bug in the parser</user_query>"}]}}
        untagged = {"role": "user", "message": {"content": [{"type": "text", "text": "no timestamp here"}]}}
        asst = {"role": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}
        _write(c, [json.dumps(tagged), json.dumps(untagged), json.dumps(asst)])
        sub = tempfile.TemporaryDirectory()
        Path(sub.name, "cur.jsonl").write_bytes(c.read_bytes())
        events, q, dropped = ingest.get("cursor")(sub.name)
        self.assertEqual(len(events), 1)
        self.assertEqual(dropped, 2)   # untagged user + assistant, both counted
        sub.cleanup()

    def test_malformed_message_shape_does_not_crash_and_is_counted(self):
        j = Path(self.tmp.name) / "badmsg.jsonl"
        _write(j, ['{"type":"user","timestamp":"2026-02-01T10:00:00Z","message":"a string not a dict"}',
                   '{"type":"user","timestamp":"2026-02-01T10:01:00Z","message":42}',
                   _cc_line("user", "a real datable operator turn here", "2026-02-01T10:02:00Z")])
        sub = tempfile.TemporaryDirectory()
        Path(sub.name, "badmsg.jsonl").write_bytes(j.read_bytes())
        # truthy non-dict message must NOT crash — it degrades to an empty-text drop
        events, q, dropped = ingest.get("claude-code")(sub.name)
        self.assertEqual(len(events), 1)
        self.assertEqual(dropped, 2)
        sub.cleanup()

    def test_same_name_files_in_different_dirs_stay_distinct_threads(self):
        root = tempfile.TemporaryDirectory()
        for sub, ts in (("projA", "2026-02-01T10:00:00Z"), ("projB", "2026-02-09T10:00:00Z")):
            Path(root.name, sub).mkdir()
            _write(Path(root.name, sub, "session.jsonl"),
                   [_cc_line("user", f"work in {sub} on the thing", ts)])
        events, q, _ = ingest.get("claude-code")(root.name)
        self.assertEqual(len({e.thread_id for e in events}), 2)   # not merged
        root.cleanup()

    def test_cursor_two_dated_blocks_get_distinct_ids(self):
        line = {"role": "user", "message": {"content": [
            {"type": "text", "text": "<timestamp>Tuesday, May 19, 2026, 12:38 PM (UTC-6)</timestamp>\n<user_query>first block query</user_query>"},
            {"type": "text", "text": "<timestamp>Tuesday, May 19, 2026, 12:40 PM (UTC-6)</timestamp>\n<user_query>second block query</user_query>"},
        ]}}
        sub = tempfile.TemporaryDirectory()
        _write(Path(sub.name, "c.jsonl"), [json.dumps(line)])
        events, q, dropped = ingest.get("cursor")(sub.name)
        self.assertEqual(len(events), 2)
        self.assertEqual(len({e.event_id for e in events}), 2)    # no collision
        sub.cleanup()

    def test_naive_timestamp_is_utc_not_host_tz(self):
        import os
        j = Path(self.tmp.name) / "naive.jsonl"
        _write(j, [_cc_line("user", "turn one is a full length prompt", "2026-02-01T10:00:00"),
                   _cc_line("user", "turn two is a full length prompt", "2026-02-01T10:05:00")])
        sub = tempfile.TemporaryDirectory()
        Path(sub.name, "naive.jsonl").write_bytes(j.read_bytes())
        old = os.environ.get("TZ")
        try:
            os.environ["TZ"] = "Asia/Kolkata"
            import time; time.tzset()
            events, q, _ = ingest.get("claude-code")(sub.name)
            deltas = [e.time.delta_prev_s for e in events if e.time.delta_prev_s is not None]
            self.assertIn(300.0, deltas)   # 5 min, independent of host TZ
        finally:
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            import time; time.tzset()
        sub.cleanup()

    def test_classifier_prose_false_positives_fixed(self):
        from corpuslens.ingest.claude_code import AUTHORED, DELIB
        for s in ["I take exception to that remark", "we waited in line 40 minutes at the DMV",
                  "a strong sense of self. Then it faded", "I made an exception for him"]:
            self.assertFalse(CODE_REF.search(s), f"CODE_REF FP: {s}")
        for s in ["Budget = 500 dollars this month", "weight = 180 lbs today", "  return to sender please"]:
            self.assertFalse(AUTHORED.search(s), f"AUTHORED FP: {s}")
        for s in ["my stock options vested today", "thoughts and prayers to the family"]:
            self.assertFalse(DELIB.search(s), f"DELIB FP: {s}")
        # round-4 prose false positives (plural-paren, import-prose)
        for s in ["make some change(s) to it", "bring the kids(!) along", "several meeting(s) this week"]:
            self.assertFalse(CODE_REF.search(s), f"CODE_REF plural-paren FP: {s}")
        for s in ["import export business is booming", "import duty is high on that",
                  "from home import lessons for the kids too"]:
            self.assertFalse(AUTHORED.search(s), f"AUTHORED import-prose FP: {s}")
        # real code still caught
        self.assertTrue(AUTHORED.search("SELECT id FROM users WHERE active = true"))
        self.assertTrue(AUTHORED.search("public class Foo {"))
        self.assertTrue(AUTHORED.search("for i in range(10):"))

    def test_out_of_range_date_is_dropped_not_crash(self):
        j = Path(self.tmp.name) / "baddate.jsonl"
        _write(j, [_cc_line("user", "corrupt month thirteen timestamp here", "2026-13-01T10:00:00Z"),
                   _cc_line("user", "a valid datable operator turn here", "2026-02-01T10:00:00Z")])
        sub = tempfile.TemporaryDirectory()
        Path(sub.name, "baddate.jsonl").write_bytes(j.read_bytes())
        events, q, dropped = ingest.get("claude-code")(sub.name)   # must not raise
        self.assertEqual(len(events), 1)
        self.assertEqual(dropped, 1)
        sub.cleanup()

    def test_pure_prose_corpus_reads_low_authored(self):
        # the flagship honesty case: a zero-code personal corpus must NOT score
        # as more code-authored than the coding reference population
        j = Path(self.tmp.name) / "personal.jsonl"
        prose = ["let me know if that works for you tomorrow",
                 "let it go, we can figure out dinner later",
                 "static electricity made her hair stand up at the park",
                 "var was short for variance in the old statistics textbook",
                 "thoughts and prayers to the family this week",
                 "my stock options vested today which was a relief",
                 "if the weather is nice tomorrow, we could go to the park:"]
        _write(j, [_cc_line("user", t, f"2026-02-0{i+1}T10:00:00Z") for i, t in enumerate(prose)])
        sub = tempfile.TemporaryDirectory()
        Path(sub.name, "personal.jsonl").write_bytes(j.read_bytes())
        events, q, _ = ingest.get("claude-code")(sub.name)
        from corpuslens.analyze.composition import composition_mix
        res = composition_mix(events)
        self.assertLess(res["authored_code_pct"], 14.5)   # below the coding-pop reference
        self.assertEqual(res["authored_code_pct"], 0.0)
        sub.cleanup()

    def test_adapter_rejects_file_path_at_library_boundary(self):
        f = Path(self.tmp.name) / "s1.jsonl"
        with self.assertRaises(NotADirectoryError):
            ingest.get("claude-code")(str(f))

    def test_denominatorless_analyzer_rejected(self):
        with self.assertRaises(ValueError):
            register("bad", claims=("tempo",), denominator=" ")(lambda ev: {})

    def test_empty_and_missing_paths_exit_nonzero(self):
        empty = tempfile.TemporaryDirectory()
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli_main(["run", empty.name, "--adapter", "claude-code"])
        self.assertEqual(rc, 1)               # matched nothing -> error, not cheerful 0
        empty.cleanup()
        err2 = io.StringIO()
        with redirect_stderr(err2):
            rc2 = cli_main(["run", "/no/such/path/xyz", "--adapter", "claude-code"])
        self.assertEqual(rc2, 2)              # missing path -> usage error
        self.assertIn("does not exist", err2.getvalue())

    def test_file_instead_of_dir_is_rejected(self):
        f = Path(self.tmp.name) / "s1.jsonl"
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli_main(["run", str(f), "--adapter", "claude-code"])
        self.assertEqual(rc, 2)
        self.assertIn("directory", err.getvalue())


if __name__ == "__main__":
    unittest.main()
