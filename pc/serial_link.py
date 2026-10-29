"""UNO와의 115200 줄 단위 JSON 통신. 출력 명령은 자동 재전송하지 않는다."""
import json
import threading
import time

ACK_TIMEOUT = 2.0
RECONNECT_DELAY = 3.0
BOOT_WAIT = 2.0  # 포트를 열면 UNO가 재시작함


def parse_line(raw):
    try:
        msg = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(msg, dict) or msg.get("v") != 1 or "type" not in msg:
        return None
    return msg


class Link:
    def __init__(self, port_factory, on_message, clock=time.monotonic):
        self.port_factory, self.on_message, self.clock = port_factory, on_message, clock
        self.port = None
        self.last_rx = None
        self.unconfirmed = 0
        self.bad_lines = 0
        self._next = 1
        self._pending = {}
        self._lock = threading.Lock()

    def send(self, cmd):
        with self._lock:
            n = self._next
            self._next = 1 if n >= 65535 else n + 1
            self._pending[n] = self.clock()
            port = self.port
        if port is not None:
            try:
                port.write(f"{n} {cmd}\n".encode("ascii"))
            except Exception:
                pass  # 읽기 루프가 끊김을 감지해 재연결함
        return n

    def poll_timeouts(self):
        now = self.clock()
        with self._lock:
            late = [n for n, t in self._pending.items() if now - t > ACK_TIMEOUT]
            for n in late:
                del self._pending[n]
            self.unconfirmed += len(late)
        return late

    def handle(self, raw):
        msg = parse_line(raw.strip())
        if msg is None:
            if raw.strip():
                self.bad_lines += 1
            return
        self.last_rx = self.clock()
        if msg["type"] in ("ack", "error"):
            with self._lock:
                self._pending.pop(msg.get("request"), None)
        self.on_message(msg)

    def run_forever(self, stop):
        while not stop.is_set():
            try:
                port = self.port_factory()
            except Exception as e:
                busy = isinstance(e, PermissionError) or "denied" in str(e).lower() or "access" in str(e).lower()
                self.on_message({"type": "link", "state": "down", "reason": "busy" if busy else "missing"})
                stop.wait(RECONNECT_DELAY)
                continue
            self.port = port
            stop.wait(BOOT_WAIT)
            self.on_message({"type": "link", "state": "up"})
            self.send("STATUS")
            try:
                while not stop.is_set():
                    self.handle(port.readline())
            except Exception:
                self.on_message({"type": "link", "state": "down", "reason": "missing"})
            finally:
                self.port = None
                try:
                    port.close()
                except Exception:
                    pass
            stop.wait(RECONNECT_DELAY)
