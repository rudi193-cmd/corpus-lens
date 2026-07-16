"""The acceptance tests for the centerpiece: prove the wall, then trust it.

Red-team spirit (build-sequence step 5, run first here): the custody-shaped
analysis must be UN-ASSEMBLABLE in the default profile — not refused politely,
structurally unreachable — and every door must fail closed.
"""
import unittest

from corpuslens.guard import DEFAULT_PROFILE, Guard, Profile, WallError
from corpuslens.model import CoarseTime, Event, Quarantine
from corpuslens.analyze import Analyzer


def _q():
    return Quarantine(base_date_iso="2026-01-05", local_tz="America/Denver")


class WallTests(unittest.TestCase):
    def test_default_profile_grants_nothing(self):
        self.assertEqual(DEFAULT_PROFILE.capabilities, frozenset())

    def test_calendar_denied_by_default(self):
        g = Guard(_q())
        with self.assertRaises(WallError):
            g.release("calendar_time", "I would like the dates")

    def test_unknown_capability_is_denial(self):
        g = Guard(_q(), Profile(name="x", capabilities=frozenset({"calendar_time"}), owner_token="t"))
        with self.assertRaises(WallError):
            g.release("wall_hack", "please")

    def test_missing_justification_is_denial(self):
        g = Guard(_q(), Profile(name="x", capabilities=frozenset({"calendar_time"}), owner_token="t"))
        with self.assertRaises(WallError):
            g.release("calendar_time", "   ")

    def test_granted_without_owner_token_is_denial(self):
        g = Guard(_q(), Profile(name="x", capabilities=frozenset({"calendar_time"})))
        with self.assertRaises(WallError):
            g.release("calendar_time", "legit reason")

    def test_full_grant_releases_and_audits(self):
        g = Guard(_q(), Profile(name="x", capabilities=frozenset({"calendar_time"}), owner_token="t"))
        self.assertEqual(g.release("calendar_time", "demo"), "2026-01-05")
        self.assertTrue(any("calendar_time" in s for s in g.audit.granted))

    def test_event_carries_no_calendar(self):
        e = Event(event_id="e", corpus_id="c", adapter_id="a/1", source_ref="f:1",
                  thread_id="t", surface="cli", author_class="operator",
                  data_type="prompt", time=CoarseTime(day_offset=3))
        blob = repr(e.__dict__) + repr(e.time)
        for leak in ("2026", "Monday", "tz", "hour"):
            self.assertNotIn(leak, blob)

    def test_person_claim_unregisterable_by_default(self):
        g = Guard(_q())
        spy = Analyzer(name="custody_map", claims=("life_partition",),
                       denominator="events", run=lambda ev: {})
        self.assertFalse(g.admit(spy))
        self.assertTrue(g.audit.analyzers_refused)

    def test_unknown_claim_refused(self):
        g = Guard(_q())
        weird = Analyzer(name="vibes", claims=("who_he_is",),
                         denominator="events", run=lambda ev: {})
        self.assertFalse(g.admit(weird))

    def test_custody_unassemblable_end_to_end(self):
        """The 7-finding attack needs weekday x hour. From Events under the
        default profile there is no path to either: no calendar anchor, no tz,
        no hour — only day offsets and deltas. Assert the raw materials are
        absent, not just gated."""
        g = Guard(_q())
        with self.assertRaises(WallError):
            g.release("calendar_time", "attack")
        with self.assertRaises(WallError):
            g.release("local_tz", "attack")
        self.assertFalse(hasattr(CoarseTime(day_offset=0), "hour"))
        self.assertFalse(hasattr(CoarseTime(day_offset=0), "weekday"))


if __name__ == "__main__":
    unittest.main()
