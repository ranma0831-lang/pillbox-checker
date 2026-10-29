import unittest

from pc.serial_link import Link, parse_line


class FakePort:
    def __init__(self, lines=()):
        self.lines, self.written = list(lines), b""

    def readline(self):
        return self.lines.pop(0) if self.lines else b""

    def write(self, b):
        self.written += b

    def close(self):
        pass


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class SerialLinkTest(unittest.TestCase):
    def setUp(self):
        self.port, self.clock, self.msgs = FakePort(), Clock(), []
        self.link = Link(lambda: self.port, self.msgs.append, clock=self.clock)
        self.link.port = self.port

    def test_parse_line_rejects_garbage(self):
        for raw in [b"\x00\xff{", b"hello", b'{"v":2,"type":"state"}', b'{"v":1}', b"", b"[1]"]:
            self.assertIsNone(parse_line(raw), raw)
        self.assertEqual(parse_line(b'{"v":1,"type":"state","lid_open":false}\r\n')["type"], "state")

    def test_send_numbers_and_wraps(self):
        self.link._next = 65535
        self.assertEqual(self.link.send("PING"), 65535)
        self.assertEqual(self.link.send("PING"), 1)
        self.assertTrue(self.port.written.endswith(b"1 PING\n"))

    def test_ack_clears_and_timeout_reported_once(self):
        a = self.link.send("DONE 1")
        b = self.link.send("MSG 2")
        self.link.handle(b'{"v":1,"type":"ack","request":%d,"applied":true}' % a)
        self.clock.t += 2.1
        self.assertEqual(self.link.poll_timeouts(), [b])
        self.assertEqual(self.link.poll_timeouts(), [])
        self.assertEqual(self.link.unconfirmed, 1)

    def test_status_reply_counts_as_response(self):
        n = self.link.send("STATUS")
        self.link.handle(b'{"v":1,"type":"state","profile":"PILL","request":%d}' % n)
        self.clock.t += 2.1
        self.assertEqual(self.link.poll_timeouts(), [])

    def test_link_up_only_after_board_speaks(self):
        port = FakePort([b"", b"\x00garbage", b'{"v":1,"type":"state","profile":"PILL","request":0}\n'])
        stop = __import__("threading").Event()
        msgs = []
        link = Link(lambda: port, lambda m: (msgs.append(m), m.get("type") == "state" and stop.set()), clock=self.clock)
        link.boot_wait = 0
        link.run_forever(stop)
        self.assertEqual([m["type"] for m in msgs][:2], ["state", "link"])  # 보드가 말한 뒤에 연결됨
        self.assertIn(b"STATUS", port.written)

    def test_no_pending_when_port_missing(self):
        self.link.port = None
        self.link.send("PING")
        self.clock.t += 2.1
        self.assertEqual(self.link.poll_timeouts(), [])

    def test_handle_counts_bad_lines_and_forwards_good(self):
        self.link.handle(b"garbage")
        self.link.handle(b'{"v":1,"type":"event","event":"press","ms":5}')
        self.assertEqual(self.link.bad_lines, 1)
        self.assertEqual(self.msgs[-1]["event"], "press")
        self.assertEqual(self.link.last_rx, 100.0)


if __name__ == "__main__":
    unittest.main()
