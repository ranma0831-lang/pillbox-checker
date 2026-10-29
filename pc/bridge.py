"""약 복용 확인 상자 PC 프로그램: 시리얼 · 판정 · 기록 · 웹(같은 Wi-Fi).

실행: python pc/bridge.py --port COM5    /    보드 없이: python pc/bridge.py --demo
"""
import argparse
import json
import mimetypes
import secrets
import socket
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

if __package__ in (None, ""):  # python pc/bridge.py 로 실행할 때
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pc import store
from pc.judge import WINDOW_BEFORE, judge, outputs, parse_hhmm

STALE_S = 60
PING_S = 3


def _minute(dt):
    return dt.hour * 60 + dt.minute


class App:
    def __init__(self, data_dir, send, clock, demo=False):
        self.data_dir, self.send, self.clock, self.demo = Path(data_dir), send, clock, demo
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.rec_path = self.data_dir / "records.jsonl"
        self.set_path = self.data_dir / "settings.json"
        self.records = store.load(self.rec_path, clock())
        self.settings = store.load_settings(self.set_path)
        self.link_up, self.reason = False, "missing"
        self.last_rx = None
        self._sent_out = None  # None이면 다음 tick에 출력 전체를 보냄
        self._last_ping = None
        self._lock = threading.RLock()

    # ---- 기록 ----
    def _append(self, event, **extra):
        t = self.clock()
        store.append(self.rec_path, event, t, **extra)
        self.records.append({"t": t.strftime("%Y-%m-%dT%H:%M:%S"), "e": event, "_dt": t.replace(microsecond=0), **extra})

    @property
    def dose(self):
        return parse_hhmm(self.settings["dose_time"])

    def on_message(self, msg):
        with self._lock:
            kind = msg.get("type")
            if kind == "link":
                self.link_up = msg["state"] == "up"
                if self.link_up:
                    self._sent_out = None
                    self._append("connect")
                else:
                    self.reason = msg.get("reason", "missing")
                    self._append("disconnect", reason=self.reason)
                return
            if kind == "unconfirmed":
                self._append("unconfirmed", request=msg.get("request"))
                return
            self.last_rx = self.clock()
            if kind == "state" and self._sent_out is not None:
                board = {"REMIND": msg.get("remind"), "DONE": msg.get("done"), "MSG": msg.get("msg")}
                if any(v is not None and v != self._sent_out[k] for k, v in board.items()):
                    self._sent_out = None  # 보드가 보고한 출력이 판정과 다르면 다음 tick에 다시 맞춤
            if kind == "event":
                ev = msg.get("event")
                if ev == "press":
                    early = _minute(self.clock()) < self.dose - WINDOW_BEFORE
                    self._append("early_press" if early else "press")
                elif ev in ("lid_open", "lid_close"):
                    self._append(ev)

    # ---- 판정 ----
    def _stale(self, now):
        return self.last_rx is None or (now - self.last_rx).total_seconds() > STALE_S

    def _today(self, now):
        presses = store.presses_by_day(self.records).get(now.date(), [])
        return judge(presses, self.dose, _minute(now), stale=self._stale(now), grace=self.settings["grace_min"])

    def tick(self):
        with self._lock:
            if not self.link_up:  # 끊긴 보드에 보낸 명령은 모두 '미확인'으로 쌓이기만 함
                return
            now = self.clock()
            v = self._today(now)
            if v["status"] != "unknown":  # 보드와 끊긴 동안은 출력 명령을 보내지 않음
                dose = self.dose
                want = {**outputs(v["status"], _minute(now), dose),
                        "DOSE": f"{dose // 60:02d}{dose % 60:02d}",  # LCD에 보여 줄 복용·확인 시각 (보드엔 시계가 없음)
                        "TAKEN": "-1" if v["at"] is None else f"{v['at'] // 60:02d}{v['at'] % 60:02d}"}
                for k, val in want.items():
                    if self._sent_out is None or self._sent_out.get(k) != val:
                        self.send(f"{k} {val}")
                self._sent_out = want
            if self._last_ping is None or (now - self._last_ping).total_seconds() >= PING_S:
                self._last_ping = now
                self.send("PING")

    def set_dose(self, dose_time):
        with self._lock:
            prev = self.settings["dose_time"]
            self.settings = store.save_settings(self.set_path, dose_time)
            self._append("setting", dose_time=dose_time, prev=prev)
            self._sent_out = None

    def ack(self):
        with self._lock:
            if self._today(self.clock())["status"] not in ("caution", "warning"):
                raise ValueError("지금은 확인할 알림이 없습니다")
            self._append("ack")
            return self.state()

    def dose_on(self, day):
        """그날 적용된 복용 시각: 그날까지의 마지막 변경, 없으면 첫 변경 전 값, 기록이 없으면 현재 값."""
        changes = [r for r in self.records if r["e"] == "setting" and isinstance(r.get("dose_time"), str)]
        before = [r for r in changes if r["_dt"].date() <= day]
        if before:
            return before[-1]["dose_time"]
        if changes and isinstance(changes[0].get("prev"), str):
            return changes[0]["prev"]
        return self.settings["dose_time"]

    # ---- API ----
    def _events(self, day):
        return [{"t": r["_dt"].strftime("%H:%M"), "e": r["e"]} for r in self.records if r["_dt"].date() == day]

    def state(self):
        with self._lock:
            now = self.clock()
            v = self._today(now)
            today = [r for r in self.records if r["_dt"].date() == now.date()]
            acks = [r["_dt"] for r in today if r["e"] == "ack"]
            alert = v["status"] if v["status"] in ("caution", "warning", "unknown") else "none"
            age = None if self.last_rx is None else round((now - self.last_rx).total_seconds())
            return {
                "date": now.date().isoformat(), "now": now.strftime("%H:%M"),
                "dose_time": self.settings["dose_time"], "status": v["status"],
                "at": None if v["at"] is None else f"{v['at'] // 60:02d}:{v['at'] % 60:02d}",
                "early": [f"{m // 60:02d}:{m % 60:02d}" for m in v["early"]],
                "lid_events": [r["_dt"].strftime("%H:%M") for r in today if r["e"] == "lid_open"],
                "alert": alert, "acked_at": acks[0].strftime("%H:%M") if acks else None,
                "board": {"connected": self.link_up and not self._stale(now), "last_rx_age_s": age,
                          "reason": None if self.link_up else self.reason},
                "events": self._events(now.date()), "demo": self.demo,
            }

    def history(self, days):
        with self._lock:
            days = max(1, min(90, days))
            now = self.clock()
            presses = store.presses_by_day(self.records)
            has = store.days_with_records(self.records)
            out = []
            for i in range(days - 1, -1, -1):
                d = now.date() - timedelta(days=i)
                if d == now.date():
                    v = self._today(now)
                else:
                    v = judge(presses.get(d, []), parse_hhmm(self.dose_on(d)), None, has_records=d in has, grace=self.settings["grace_min"])
                out.append({"date": d.isoformat(), "status": v["status"],
                            "dose_time": self.settings["dose_time"] if d == now.date() else self.dose_on(d),
                            "at": None if v["at"] is None else f"{v['at'] // 60:02d}:{v['at'] % 60:02d}",
                            "events": self._events(d)})
            return out


def make_server(app, token, web_dir, port):
    web_dir = Path(web_dir).resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authed(self, q):
            if not secrets.compare_digest(q.get("k", [""])[0], token):
                self._json(403, {"error": "접속 주소를 다시 확인해 주세요"})
                return False
            return True

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/api/state":
                if self._authed(q):
                    self._json(200, app.state())
            elif u.path == "/api/history":
                if self._authed(q):
                    try:
                        days = int(q.get("days", ["35"])[0])
                    except ValueError:
                        days = 35
                    self._json(200, app.history(days))
            else:
                self._static(u.path)

        def do_POST(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if not self._authed(q):
                return
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(min(n, 4096)) if n else b""
            try:
                if u.path == "/api/settings":
                    body = json.loads(raw or b"null")
                    if not isinstance(body, dict) or not isinstance(body.get("dose_time"), str):
                        raise ValueError("dose_time(HH:MM)이 필요합니다")
                    app.set_dose(body["dose_time"])
                    self._json(200, app.state())
                elif u.path == "/api/ack":
                    self._json(200, app.ack())
                else:
                    self._json(404, {"error": "없는 주소입니다"})
            except ValueError as e:  # json.JSONDecodeError 포함
                self._json(400, {"error": str(e) if not isinstance(e, json.JSONDecodeError) else "JSON 형식이 아닙니다"})

        def _static(self, path):
            target = (web_dir / (path.lstrip("/") or "index.html")).resolve()
            if web_dir not in target.parents and target != web_dir / "index.html" or not target.is_file():
                self.send_error(404)
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", (mimetypes.guess_type(target.name)[0] or "application/octet-stream") + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # 패킷은 보내지 않고 경로만 고름
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def seed_demo(app):
    """연습 데이터: 지난 30일 + 오늘은 뚜껑만 두 번 열고 확인 없음."""
    import random
    rnd = random.Random(7)
    now = app.clock()
    dose = now - timedelta(minutes=67)
    app.settings = store.save_settings(app.set_path, dose.strftime("%H:%M"))
    lines = []
    for i in range(30, 0, -1):
        d = (now - timedelta(days=i)).replace(second=0, microsecond=0)
        if i == 7:
            continue  # PC가 꺼진 날
        base = d.replace(hour=dose.hour, minute=dose.minute)
        if i in (12, 26):
            lines += [(base + timedelta(minutes=5), "lid_open"), (base + timedelta(minutes=50), "lid_open"), (base + timedelta(minutes=75), "ack")]
            continue
        c = base + timedelta(minutes=rnd.randint(-10, 30) if i != 20 else 80)
        lines += [(c - timedelta(minutes=3), "lid_open"), (c - timedelta(minutes=2), "lid_close"), (c, "press")]
    lines += [(now - timedelta(minutes=62), "lid_open"), (now - timedelta(minutes=61), "lid_close"), (now - timedelta(minutes=26), "lid_open"), (now - timedelta(minutes=25), "lid_close")]
    for t, e in sorted(lines):
        store.append(app.rec_path, e, t)
    app.records = store.load(app.rec_path, now)


def main():
    for s in (sys.stdout, sys.stderr):  # Windows 콘솔(cp949)에서 출력 못 하는 글자로 죽지 않게
        s.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description="약 복용 확인 상자 PC 프로그램")
    ap.add_argument("--port", help="보드 시리얼 포트 (예: COM5)")
    ap.add_argument("--http", type=int, default=8000)
    ap.add_argument("--demo", action="store_true", help="보드 없이 연습 데이터로 실행")
    a = ap.parse_args()
    if not a.port and not a.demo:
        ap.error("--port 또는 --demo 가 필요합니다")

    here = Path(__file__).resolve().parent
    token = f"{secrets.randbelow(10**6):06d}"
    stop = threading.Event()

    if a.demo:
        import shutil
        data = here / "demo-data"
        shutil.rmtree(data, ignore_errors=True)
        app = App(data, lambda c: 0, datetime.now, demo=True)
        seed_demo(app)
        app.on_message({"type": "link", "state": "up"})
        link = None
    else:
        import serial
        from pc.serial_link import Link
        holder = {}
        link = Link(lambda: serial.Serial(a.port, 115200, timeout=0.2), lambda m: holder["app"].on_message(m))
        app = App(here, link.send, datetime.now)
        holder["app"] = app
        threading.Thread(target=link.run_forever, args=(stop,), daemon=True).start()

    srv = make_server(app, token, here.parent / "web", a.http)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"휴대폰(같은 Wi-Fi)에서 열기: http://{lan_ip()}:{a.http}/?k={token}", flush=True)
    print("이 주소를 가족에게만 보내세요. 종료: Ctrl+C", flush=True)
    try:
        while True:
            if link:
                for n in link.poll_timeouts():
                    app.on_message({"type": "unconfirmed", "request": n})
            else:
                app.on_message({"v": 1, "type": "state"})  # 연습 모드: 보드가 살아 있는 것처럼
            app.tick()
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
        srv.shutdown()


if __name__ == "__main__":
    main()
