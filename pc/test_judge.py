import unittest

from pc.judge import judge, outputs, parse_hhmm


class JudgeTest(unittest.TestCase):
    def test_window_boundary(self):
        self.assertEqual(judge([359], 480, 547)["status"], "warning")
        self.assertEqual(judge([359], 480, 547)["early"], [359])
        self.assertEqual(judge([360], 480, 547)["status"], "done")

    def test_done_vs_late(self):
        self.assertEqual(judge([510], 480, None)["status"], "done")
        self.assertEqual(judge([511], 480, None)["status"], "late")

    def test_stages(self):
        for now, st in [(359, "before"), (360, "window"), (480, "due"), (509, "due"),
                        (510, "caution"), (539, "caution"), (540, "warning")]:
            self.assertEqual(judge([], 480, now)["status"], st, now)

    def test_past_days(self):
        self.assertEqual(judge([], 480, None)["status"], "missed")
        self.assertEqual(judge([], 480, None, has_records=False)["status"], "none")

    def test_stale_is_unknown_unless_done(self):
        self.assertEqual(judge([], 480, 547, stale=True)["status"], "unknown")
        self.assertEqual(judge([492], 480, 547, stale=True)["status"], "done")

    def test_first_valid_press_wins(self):
        self.assertEqual(judge([492, 600], 480, 700)["at"], 492)

    def test_dose_change_rejudges(self):
        r = judge([400], 540, 600)  # 복용 09:00 → 인정 07:00, 06:40 누름은 early
        self.assertEqual((r["status"], r["early"]), ("warning", [400]))

    def test_outputs(self):
        self.assertEqual(outputs("done"), {"REMIND": 0, "DONE": 1, "WINDOW": 1, "MSG": 2})
        self.assertEqual(outputs("caution"), {"REMIND": 1, "DONE": 0, "WINDOW": 1, "MSG": 4})
        self.assertEqual(outputs("before"), {"REMIND": 0, "DONE": 0, "WINDOW": 0, "MSG": 0})

    def test_red_led_starts_three_minutes_after_dose(self):
        self.assertEqual(outputs("due", 482, 480), {"REMIND": 0, "DONE": 0, "WINDOW": 1, "MSG": 1})
        self.assertEqual(outputs("due", 483, 480), {"REMIND": 1, "DONE": 0, "WINDOW": 1, "MSG": 4})

    def test_parse_hhmm(self):
        self.assertEqual(parse_hhmm("08:00"), 480)
        for bad in ["8:00x", "24:00", "07:60", "", "ab:cd"]:
            with self.assertRaises(ValueError):
                parse_hhmm(bad)


if __name__ == "__main__":
    unittest.main()
