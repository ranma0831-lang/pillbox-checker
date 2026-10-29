import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from pc.bridge import App, make_server


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def at(self, h, m, s=0, day=29):
        self.t = datetime(2026, 10, day, h, m, s)


class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock(datetime(2026, 10, 29, 6, 0))
        self.sent = []
        self.app = App(Path(self.tmp.name), lambda c: self.sent.append(c) or len(self.sent), self.clock)
        self.app.on_message({"type": "link", "state": "up"})

    def tearDown(self):
        self.tmp.cleanup()

    def alive(self):
        self.app.on_message({"v": 1, "type": "state", "lid_open": False})

    def test_press_in_window_marks_done_and_sends(self):
        self.clock.at(8, 12)
        self.app.on_message({"v": 1, "type": "event", "event": "press"})
        self.app.tick()
        self.assertEqual(self.app.state()["status"], "done")
        self.assertIn("DONE 1", self.sent)
        self.assertIn("MSG 2", self.sent)

    def test_sends_dose_and_taken_times(self):
        self.clock.at(7, 0)
        self.alive()
        self.app.tick()
        self.assertIn("DOSE 0800", self.sent)
        self.assertIn("TAKEN -1", self.sent)
        self.clock.at(8, 12)
        self.app.on_message({"v": 1, "type": "event", "event": "press"})
        self.app.tick()
        self.assertIn("TAKEN 0812", self.sent)

    def test_red_led_waits_three_minutes(self):
        self.clock.at(8, 2, 59)
        self.alive()
        self.app.tick()
        self.assertNotIn("REMIND 1", self.sent)
        self.clock.at(8, 3)
        self.alive()
        self.app.tick()
        self.assertIn("REMIND 1", self.sent)
        self.assertIn("MSG 4", self.sent)

    def test_early_press_recorded_not_counted(self):
        self.clock.at(5, 41)
        self.app.on_message({"v": 1, "type": "event", "event": "press"})
        st = self.app.state()
        self.assertEqual(st["status"], "before")
        self.assertEqual(st["early"], ["05:41"])
        self.assertIn('"e": "early_press"', (Path(self.tmp.name) / "records.jsonl").read_text(encoding="utf-8"))

    def test_only_changed_outputs_sent(self):
        self.clock.at(7, 0)
        self.alive()
        self.app.tick()
        self.sent.clear()
        self.clock.at(7, 0, 1)
        self.alive()
        self.app.tick()
        self.assertEqual([c for c in self.sent if c != "PING"], [])

    def test_midnight_resets_outputs(self):
        self.clock.at(8, 12)
        self.app.on_message({"v": 1, "type": "event", "event": "press"})
        self.clock.at(23, 59)
        self.alive()
        self.app.tick()
        self.sent.clear()
        self.clock.t = datetime(2026, 10, 30, 0, 0, 1)
        self.alive()
        self.app.tick()
        self.assertIn("DONE 0", self.sent)
        self.assertEqual(self.app.state()["status"], "before")

    def test_stale_becomes_unknown(self):
        self.clock.at(8, 35)
        self.alive()
        self.clock.at(8, 36, 2)
        self.assertEqual(self.app.state()["alert"], "unknown")

    def test_ack_only_when_alerting(self):
        self.clock.at(7, 0)
        self.alive()
        with self.assertRaises(ValueError):
            self.app.ack()
        self.clock.at(8, 35)
        self.alive()
        self.app.ack()
        self.assertEqual(self.app.state()["acked_at"], "08:35")

    def test_dose_change_resends_outputs(self):
        self.clock.at(8, 40)
        self.alive()
        self.app.tick()
        self.assertIn("REMIND 1", self.sent)
        self.app.set_dose("10:00")
        self.app.tick()
        self.assertIn("REMIND 0", self.sent)


class ReviewFixTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock(datetime(2026, 10, 27, 8, 5))
        self.sent = []
        self.app = App(Path(self.tmp.name), lambda c: self.sent.append(c) or len(self.sent), self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def test_nothing_sent_while_link_down(self):
        self.app.on_message({"type": "link", "state": "down", "reason": "missing"})
        self.app.tick()
        self.assertEqual(self.sent, [])

    def test_dose_change_keeps_past_days(self):
        self.app.on_message({"type": "link", "state": "up"})
        for day in (27, 28):
            self.clock.at(8, 5, day=day)
            self.app.on_message({"v": 1, "type": "event", "event": "press"})
        self.clock.at(12, 0, day=29)
        self.app.set_dose("20:00")
        past = {d["date"]: d["status"] for d in self.app.history(3)}
        self.assertEqual(past["2026-10-27"], "done")
        self.assertEqual(past["2026-10-28"], "done")
        self.assertEqual(self.app.history(1)[0]["dose_time"], "20:00")

    def test_board_state_mismatch_triggers_resend(self):
        self.app.on_message({"type": "link", "state": "up"})
        self.clock.at(8, 12)
        self.app.on_message({"v": 1, "type": "event", "event": "press"})
        self.app.tick()
        self.sent.clear()
        self.app.on_message({"v": 1, "type": "state", "remind": 0, "done": 0, "msg": 0})  # DONE 1이 유실됨
        self.app.tick()
        self.assertIn("DONE 1", self.sent)

    def test_record_without_event_does_not_crash(self):
        (Path(self.tmp.name) / "records.jsonl").write_text('{"t":"2026-10-27T08:00:00"}\n{"t":"2026-10-27T08:00:00+09:00","e":"press"}\n', encoding="utf-8")
        app = App(Path(self.tmp.name), lambda c: 0, self.clock)
        app.tick()
        self.assertEqual(app.state()["status"], "unknown")


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.clock = Clock(datetime(2026, 10, 29, 8, 35))
        cls.app = App(Path(cls.tmp.name), lambda c: 1, cls.clock)
        web = Path(cls.tmp.name) / "web"
        web.mkdir()
        (web / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
        cls.srv = make_server(cls.app, "4821", web, 0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def req(self, path, body=None):
        r = urllib.request.Request(self.base + path, data=body, method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_api_requires_token(self):
        self.assertEqual(self.req("/api/state")[0], 403)
        self.assertEqual(self.req("/api/state?k=0000")[0], 403)
        code, body = self.req("/api/state?k=4821")
        self.assertEqual(code, 200)
        for key in ["date", "now", "dose_time", "status", "at", "early", "lid_events", "alert", "acked_at", "board", "demo"]:
            self.assertIn(key, json.loads(body))

    def test_settings_bad_body_400(self):
        for body in [b"abc", b"", b'{"dose_time":"25:00"}', b"[]"]:
            self.assertEqual(self.req("/api/settings?k=4821", body)[0], 400, body)
        self.assertEqual(self.req("/api/state?k=4821")[0], 200)

    def test_history_clamps_days(self):
        code, body = self.req("/api/history?k=4821&days=500")
        self.assertEqual(code, 200)
        self.assertLessEqual(len(json.loads(body)), 90)

    def test_static_index_and_no_escape(self):
        self.assertEqual(self.req("/?k=4821"), (200, b"<h1>ok</h1>"))
        self.assertEqual(self.req("/../store.py?k=4821")[0], 404)


if __name__ == "__main__":
    unittest.main()
