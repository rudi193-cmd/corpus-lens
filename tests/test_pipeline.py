"""End-to-end smoke: synthetic claude-code corpus -> events -> analyzers -> report."""
import json
import tempfile
import unittest
from pathlib import Path

from corpuslens import ingest
from corpuslens.analyze import all_analyzers, register
from corpuslens.guard import Guard
from corpuslens.render import markdown


def _write_session(d: Path, name: str, turns):
    with (d / f"{name}.jsonl").open("w") as f:
        for i, (role, text, ts) in enumerate(turns):
            f.write(json.dumps({
                "type": role, "timestamp": ts,
                "message": {"content": [{"type": "text", "text": text}]}}) + "\n")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = Path(self.dir.name)
        _write_session(d, "s1", [
            ("user", "build the parser for the config file", "2026-02-01T10:00:00Z"),
            ("assistant", "Done. Should I also add validation, or keep it minimal?", "2026-02-01T10:05:00Z"),
            ("user", "it still fails on empty input, fix that", "2026-02-01T10:20:00Z"),
            ("assistant", "Fixed the empty-input path.", "2026-02-01T10:25:00Z"),
            ("user", "lets talk about options for the cache layer", "2026-02-03T09:00:00Z"),
        ])
        _write_session(d, "s2", [
            ("user", "<system-reminder>injected</system-reminder> what does mastery.py return on line 40?", "2026-02-02T08:00:00Z"),
            ("assistant", "It returns the posterior.", "2026-02-02T08:01:00Z"),
        ])

    def tearDown(self):
        self.dir.cleanup()

    def test_ingest_strips_injection_and_quarantines_calendar(self):
        events, q, dropped = ingest.get("claude-code")(self.dir.name)
        self.assertEqual(q.base_date_iso, "2026-02-01")
        self.assertTrue(all(e.time.day_offset in (0, 1, 2) for e in events))
        s2_user = [e for e in events if e.thread_id == "s2" and e.author_class == "operator"]
        self.assertTrue(s2_user[0].features["injected_stripped"])
        self.assertTrue(s2_user[0].features["code_ref"])

    def test_battery_runs_and_report_renders(self):
        events, q, dropped = ingest.get("claude-code")(self.dir.name)
        guard = Guard(q)
        guard.audit.n_events = len(events)
        results = {}
        for a in all_analyzers():
            self.assertTrue(guard.admit(a))
            results[a.name] = a.run(events)
            guard.audit.analyzers_run.append(a.name)
        self.assertEqual(results["steering_density"]["sessions"], 2)
        self.assertGreater(results["steering_density"]["mid_task_share_pct"], 0)
        self.assertEqual(results["thread_shape"]["threads"], 2)
        self.assertEqual(results["thread_shape"]["resumptions_ge2d"], 1)
        self.assertGreaterEqual(results["composition_mix"]["delib_pct"], 1)
        self.assertGreater(results["clarification_pull"]["clarification_forks_pct"], 0)
        report = markdown(results, guard.audit)
        self.assertIn("No content and no calendar position left the wall", report)

    def test_denominatorless_analyzer_rejected(self):
        with self.assertRaises(ValueError):
            register("bad", claims=("tempo",), denominator=" ")(lambda ev: {})


if __name__ == "__main__":
    unittest.main()
