import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from pc import store

NOW = datetime(2026, 10, 29, 9, 7)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.rec = self.dir / "records.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_prunes_older_than_90_days(self):
        store.append(self.rec, "press", NOW - timedelta(days=91))
        store.append(self.rec, "press", NOW)
        self.assertEqual(len(store.load(self.rec, NOW)), 1)
        self.assertEqual(len(self.rec.read_text(encoding="utf-8").splitlines()), 1)

    def test_skips_broken_lines(self):
        store.append(self.rec, "press", NOW)
        with self.rec.open("a", encoding="utf-8") as f:
            f.write('{"t":\n')
        store.append(self.rec, "lid_open", NOW)
        self.assertEqual([r["e"] for r in store.load(self.rec, NOW)], ["press", "lid_open"])

    def test_presses_by_day(self):
        store.append(self.rec, "lid_open", NOW.replace(hour=8, minute=9))
        store.append(self.rec, "press", NOW.replace(hour=8, minute=12))
        store.append(self.rec, "early_press", NOW.replace(hour=5, minute=41))
        recs = store.load(self.rec, NOW)
        self.assertEqual(store.presses_by_day(recs), {NOW.date(): [341, 492]})
        self.assertEqual(store.days_with_records(recs), {NOW.date()})

    def test_settings_default_and_validation(self):
        p = self.dir / "settings.json"
        self.assertEqual(store.load_settings(p), {"dose_time": "08:00", "grace_min": 30})
        with self.assertRaises(ValueError):
            store.save_settings(p, "25:00")
        self.assertFalse(p.exists())
        self.assertEqual(store.save_settings(p, "09:30")["dose_time"], "09:30")
        self.assertEqual(store.load_settings(p)["dose_time"], "09:30")


if __name__ == "__main__":
    unittest.main()
