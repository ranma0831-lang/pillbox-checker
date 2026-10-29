# 약 복용 확인 상자 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** UNO 상자(LED·버튼·기울기·LCD)의 복용 확인을 PC 프로그램이 판정·기록하고, 같은 Wi‑Fi의 가족 휴대폰 화면에 보여 준다.

**Architecture:** `pillbox.ino`는 입력 사건과 상태를 115200 JSON으로 보내고 PC 명령으로 출력을 바꾼다. `bridge.py`(표준 `http.server` + `pyserial`)가 시리얼, 판정(`judge.py`), 기록(`store.py`), API를 맡는다. `web/`은 2초마다 API를 조회한다.

**Tech Stack:** Arduino C++ (arduino-cli, hd44780 1.3.2), Python 3.12 + pyserial, 표준 `unittest`, HTML/CSS/JS (라이브러리 없음)

**Spec:** `docs/design.md` (화면 기준은 `docs/wiring/pill-mockup.html`)

## Global Constraints

- 시리얼 115200, LF, `요청번호 명령 인수`, 요청번호 1~65535. D0/D1 비움. 시작 시 LED 모두 OFF. 긴 delay 금지
- 핀: 빨강 LED D8, 초록 LED D9, 버튼 D2(INPUT_PULLUP), 기울기 D3(INPUT_PULLUP), LCD I2C A4/A5
- LCD 문장 정확히: 0 `WAITING` / 1 `TAKE MEDICINE` / 2 `DONE TODAY` / 3 `PC LOST` (영문 16자 이내)
- 판정 상수: 인정 시작 D−120분, 유예 30분, 경고 D+60분, 수신 1분 초과 unknown, 보드 PC 무명령 10초 → PC LOST, PING 3초, ACK 대기 2초(재전송 없음), 기록 90일
- 파이썬 의존성은 `pyserial`만. 테스트는 표준 `unittest`
- 모든 API는 접속 코드 `k` 필요(없거나 틀리면 403). 실행 시 무작위 4자리 이상
- `--demo`는 API에 `demo:true`, 화면에 "연습 데이터" 띠 항상 표시
- 화면 문구: "의료기기가 아닌 시연용 작품입니다." 표시. 상자 끊김 "상자 상태를 알 수 없어요", PC 끊김 "PC 프로그램에 연결할 수 없어요", 403 "접속 주소를 다시 확인해 주세요"
- 작업 폴더: `C:\Users\ranma\Downloads\kit\pillbox` (새 git 저장소). 명령은 이 폴더에서 실행

## Review Focus

1. **실행 중 자정 통과** — 프로그램을 켜 둔 채 날짜가 바뀌면 `before`로 돌아가고 DONE 0을 보내야 한다 → Task 5 `test_midnight_resets_outputs`
2. **UNO 자동 리셋 직후의 깨진 줄** — 포트를 열면 보드가 재시작해 반쪽 줄·잡음이 온다. 무시하고 계속 동작해야 한다 → Task 3 `test_parse_line_rejects_garbage`
3. **하루에 여러 번 누름** — 두 번째 이후 누름은 확인 시각을 바꾸지 않는다 → Task 1 `test_first_valid_press_wins`
4. **확인 후 복용 시각 변경** — 기록으로 다시 판정한다. 새 인정 시작 전이 된 누름은 early가 된다 → Task 1 `test_dose_change_rejudges`
5. **잘못된 요청 본문** — `POST /api/settings`에 JSON이 아닌 본문이나 빈 본문이 와도 서버가 죽지 않고 400을 준다 → Task 5 `test_settings_bad_body_400`

---

### Task 1: 판정 함수 `judge.py`

**Files:**
- Create: `pillbox/pc/judge.py`
- Test: `pillbox/pc/test_judge.py`
- Create: `pillbox/.gitignore` (`.venv/`, `__pycache__/`, `pc/records.jsonl`, `pc/settings.json`)

**Interfaces:**
- Produces:
  - `parse_hhmm(s: str) -> int` — `"08:00"` → 480. 형식이 다르거나 범위 밖이면 `ValueError`
  - `judge(presses: list[int], dose: int, now: int | None, *, has_records: bool = True, stale: bool = False, grace: int = 30) -> dict` — 반환 `{"status": str, "at": int | None, "early": list[int]}`. `presses`는 그날 누름의 자정 기준 분. `now=None`이면 지난 날. status ∈ `before window due caution warning done late missed none unknown`
  - `outputs(status: str) -> dict[str, int]` — 키 `REMIND DONE WINDOW MSG`. 설계 5장 표 그대로. `missed/none/unknown`은 `{"REMIND":0,"DONE":0,"WINDOW":0,"MSG":0}`

- [ ] **Step 1: 저장소 시작**

Run: `git init pillbox` 후 `.gitignore` 작성

- [ ] **Step 2: 실패하는 테스트 작성** (`D=480`)

```python
class JudgeTest(unittest.TestCase):
    def test_window_boundary(self):
        self.assertEqual(judge([359], 480, 547)["status"], "warning")
        self.assertEqual(judge([359], 480, 547)["early"], [359])
        self.assertEqual(judge([360], 480, 547)["status"], "done")
    def test_done_vs_late(self):
        self.assertEqual(judge([510], 480, None)["status"], "done")
        self.assertEqual(judge([511], 480, None)["status"], "late")
    def test_stages(self):
        for now, st in [(359,"before"),(360,"window"),(480,"due"),(509,"due"),(510,"caution"),(539,"caution"),(540,"warning")]:
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
        r = judge([400], 540, 600)          # 복용 09:00 → 인정 07:00, 06:40 누름은 early
        self.assertEqual((r["status"], r["early"]), ("warning", [400]))
    def test_outputs(self):
        self.assertEqual(outputs("done"), {"REMIND":0,"DONE":1,"WINDOW":1,"MSG":2})
        self.assertEqual(outputs("caution"), {"REMIND":1,"DONE":0,"WINDOW":1,"MSG":1})
        self.assertEqual(outputs("before"), {"REMIND":0,"DONE":0,"WINDOW":0,"MSG":0})
    def test_parse_hhmm(self):
        self.assertEqual(parse_hhmm("08:00"), 480)
        for bad in ["8:00x", "24:00", "07:60", "", "ab:cd"]:
            with self.assertRaises(ValueError): parse_hhmm(bad)
```

- [ ] **Step 3: 실패 확인** — Run: `py -3.12 -m unittest pc.test_judge -v` → Expected: `ImportError`
- [ ] **Step 4: 구현** — 설계 5장 규칙. `done`/`late`의 `WINDOW`는 1(확인 후 추가 누름도 초록 유지)
- [ ] **Step 5: 통과 확인** — 같은 명령 → `OK`
- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: judge rules"`

### Task 2: 기록·설정 `store.py`

**Files:**
- Create: `pillbox/pc/store.py`
- Test: `pillbox/pc/test_store.py`

**Interfaces:**
- Consumes: `parse_hhmm` (Task 1)
- Produces:
  - `append(path: Path, event: str, t: datetime, **extra) -> None` — 한 줄 `{"t":"YYYY-MM-DDTHH:MM:SS","e":event,...}`
  - `load(path: Path, now: datetime, keep_days: int = 90) -> list[dict]` — 깨진 줄은 건너뛰고 stderr 경고, 오래된 줄은 지운 뒤 파일을 다시 씀
  - `presses_by_day(records: list[dict]) -> dict[date, list[int]]`, `days_with_records(records) -> set[date]`
  - `load_settings(path: Path) -> dict` (없으면 `{"dose_time":"08:00","grace_min":30}`), `save_settings(path: Path, dose_time: str) -> dict` (`parse_hhmm`로 검사, 실패 시 `ValueError`)

- [ ] **Step 1: 실패하는 테스트** — 임시 폴더(`tempfile.TemporaryDirectory`)에서:
  - `test_prunes_older_than_90_days`: 91일 전 1줄 + 오늘 1줄 → `load` 결과 1줄, 파일도 1줄
  - `test_skips_broken_lines`: `{"t":` 같은 깨진 줄 포함 → 나머지 반환, 예외 없음
  - `test_presses_by_day`: `press` 08:12 → `{date: [492]}`, `lid_open`은 제외
  - `test_settings_default_and_validation`: 파일 없음 → 기본값, `save_settings(p,"25:00")` → `ValueError`, 파일 변경 없음
- [ ] **Step 2: 실패 확인** — `py -3.12 -m unittest pc.test_store -v` → `ImportError`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** → `OK`
- [ ] **Step 5: Commit** — `feat: records and settings store`

### Task 3: 시리얼 연결 `serial_link.py`

**Files:**
- Create: `pillbox/pc/serial_link.py`, `pillbox/pc/requirements.txt` (`pyserial==3.5`)
- Test: `pillbox/pc/test_serial_link.py`

**Interfaces:**
- Produces:
  - `parse_line(raw: bytes) -> dict | None` — UTF‑8 해석 실패, JSON 아님, `v!=1`, `type` 없음 → `None`
  - `class Link` — `__init__(self, port_factory: Callable[[], Any], on_message: Callable[[dict], None], clock=time.monotonic)`. 포트 객체는 `readline()`·`write(bytes)`·`close()`만 사용
  - `Link.send(cmd: str) -> int` — 요청번호(1→65535 순환)를 붙여 `f"{n} {cmd}\n"` 전송, 번호 반환
  - `Link.poll_timeouts() -> list[int]` — 2초 지나도 ACK 없는 번호 반환(한 번만), 재전송 없음
  - `Link.run_forever(stop: threading.Event)` — 읽기 루프. 포트 오류 시 `on_message({"type":"link","state":"down","reason":"busy"|"missing"})`, 3초 뒤 재연결. 연결되면 2초 후 `STATUS` 전송, `{"type":"link","state":"up"}`
  - `Link.last_rx: float | None`, `Link.unconfirmed: int` (카운터), `Link.bad_lines: int`
- 포트 생성은 `bridge.py`가 `lambda: serial.Serial(port, 115200, timeout=0.2)`로 넘김. `PermissionError`/`SerialException("Access is denied")` → busy, `FileNotFoundError`/그 밖 → missing

- [ ] **Step 1: 실패하는 테스트** — `FakePort`(미리 넣은 줄 목록, 쓴 바이트 기록)와 가짜 시계로:
  - `test_parse_line_rejects_garbage`: `b"\x00\xff{"`, `b"hello"`, `b'{"v":2,"type":"state"}'` → `None`; 정상 state 줄 → dict
  - `test_send_numbers_and_wraps`: 65535 다음 1
  - `test_ack_clears_and_timeout_reported_once`: `send("DONE 1")` 후 ACK 수신 → `poll_timeouts()==[]`; 다른 명령은 시계 2.1초 진행 → `[n]`, 다시 호출 → `[]`, `unconfirmed==1`
- [ ] **Step 2: 실패 확인** — `py -3.12 -m unittest pc.test_serial_link -v`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: Commit** — `feat: serial link with ack tracking`

### Task 4: 펌웨어 `pillbox.ino`

**Files:**
- Create: `pillbox/firmware/pillbox/pillbox.ino`

**Interfaces:**
- Produces: 설계 4장 계약 그대로 (`state` 1초, `event` `lid_open|lid_close|press`, `ack`/`error`, 명령 `REMIND DONE WINDOW MSG STOP STATUS PING`)
- `profile` 값 `"PILL"`. 잘못된 명령 → `{"v":1,"type":"error","request":N,"code":"bad_command"}`, 번호 없는 줄 → `"code":"bad_request"`
- 기울기 디바운스 50ms. 버튼은 뗄 때 1회 `press`. 버튼 시 `WINDOW 1`이면 초록 즉시 ON, `0`이면 150ms×2 깜빡임 후 원래 상태
- 10초 무명령 → MSG 3, REMIND 깜빡임 중지. 명령이 다시 오면 마지막 MSG 복원
- LCD: hd44780 `hd44780_I2Cexp`(주소 자동 탐지). 실패 시 `lcd_ready:false`로 계속 동작
- 입력 버퍼 최대 32바이트, 넘치면 줄 폐기 후 `bad_request` (SRAM 2KB)

- [ ] **Step 1: 라이브러리 설치** — Run: `arduino-cli lib install "hd44780@1.3.2"` → `installed`
- [ ] **Step 2: 작성 후 컴파일** — Run: `arduino-cli compile --fqbn arduino:avr:uno firmware/pillbox` → Expected: 오류 없음, 전역 변수 메모리 1500바이트 미만
- [ ] **Step 3: 업로드** — Run: `arduino-cli upload -p COM5 --fqbn arduino:avr:uno firmware/pillbox` (포트는 `arduino-cli board list`로 확인)
- [ ] **Step 4: 시리얼 모니터 확인** (115200, LF) — 각 항목을 `notes/firmware-check.md`에 결과로 적음:
  - `1 STATUS` → `"profile":"PILL"`, `request":1`
  - 뚜껑 열고 닫기 → `lid_open`/`lid_close` 각 1회 (흔들어도 1회), 방향이 반대면 코드의 `LID_OPEN_LEVEL` 상수만 바꿈
  - 버튼 길게 → `press` 1회
  - `2 WINDOW 0` 후 버튼 → 초록 두 번 깜빡임, `3 WINDOW 1` 후 버튼 → 초록 켜짐
  - `4 REMIND 1` 깜빡임, `5 MSG 1` → `TAKE MEDICINE`, `6 FOO` → error
  - 10초 대기 → `PC LOST`
- [ ] **Step 5: Commit** — `feat: pillbox firmware`

### Task 5: PC 프로그램 `bridge.py` (판정 루프 + API)

**Files:**
- Create: `pillbox/pc/bridge.py`
- Test: `pillbox/pc/test_bridge.py`

**Interfaces:**
- Consumes: `judge`, `outputs`, `parse_hhmm` (Task 1), `store` 함수들 (Task 2), `Link`, `parse_line` (Task 3)
- Produces:
  - `class App` — `__init__(self, data_dir: Path, send: Callable[[str], int], clock: Callable[[], datetime], demo: bool = False)`
  - `App.on_message(msg: dict) -> None` — `event`는 기록(`press`는 그날 인정 구간이면 `press`, 아니면 `early_press`로 기록), `link` up/down 기록, `ack`/`state`는 `last_rx` 갱신, `{"type":"unconfirmed","request":n}`은 `unconfirmed` 기록. CLI 메인 루프가 매 tick마다 `Link.poll_timeouts()` 결과를 이 형식으로 넘김
  - `App.tick() -> None` — 1초마다 호출. 오늘 판정 → `outputs` 결과가 직전과 다른 키만 `send("KEY v")`. 링크가 다시 up되면 전체 출력을 한 번 보냄. 3초마다 `PING`
  - `App.state() -> dict` — 키: `date, now, dose_time, status, at, early, lid_events, alert ("none"|"caution"|"warning"|"unknown"), acked_at, board {connected, last_rx_age_s, reason}, demo`
  - `App.history(days: int) -> list[dict]` — 날짜별 `{date, status, at, events:[{t,e}]}`. `days`는 1~90로 자름
  - `App.ack() -> dict` — caution/warning일 때만 `ack` 기록, 아니면 `ValueError`
  - `make_server(app: App, token: str, web_dir: Path, port: int) -> ThreadingHTTPServer`
  - CLI: `py -3.12 pc/bridge.py --port COM5 [--http 8000] [--demo]`. 시작 시 `http://<LAN IP>:8000/?k=<token>` 출력. `--demo`는 `Link` 대신 내장 시뮬레이터(오늘 08:05 lid_open, 08:41 lid_open, 버튼 없음)를 씀
- `stale`: `last_rx` 60초 초과. API 경로·상태 코드는 설계 6장 표 그대로. 정적 파일은 `web_dir` 밖 경로 거절

- [ ] **Step 1: 실패하는 테스트** — 가짜 시계, `send`는 리스트에 기록:
  - `test_press_in_window_marks_done_and_sends`: 08:12 `press` → `state()["status"]=="done"`, 보낸 명령에 `DONE 1`, `MSG 2`
  - `test_early_press_recorded_not_counted`: 05:41 `press` → records에 `early_press`, status `before`
  - `test_only_changed_outputs_sent`: tick 두 번 → 두 번째는 PING 외 전송 없음
  - `test_midnight_resets_outputs`: 23:59 done 상태 → 시계 00:00:01 → tick → `DONE 0` 전송, status `before`
  - `test_stale_becomes_unknown`: `last_rx` 61초 전 → alert `unknown`
  - `test_ack_only_when_alerting`: 07:00 `ack()` → `ValueError`; 08:35 → `acked_at` 설정
  - API(`make_server(..., port=0)`를 스레드로 띄우고 `urllib`):
    - `test_api_requires_token`: `k` 없음/틀림 → 403
    - `test_settings_bad_body_400`: 본문 `"abc"`, 빈 본문, `{"dose_time":"25:00"}` → 400, 서버 계속 응답
    - `test_history_clamps_days`: `days=500` → 길이 90 이하
- [ ] **Step 2: 실패 확인** — `py -3.12 -m unittest pc.test_bridge -v`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — `py -3.12 -m unittest discover -s pc -v` 전체 `OK`
- [ ] **Step 5: 데모 실행 확인** — `py -3.12 pc/bridge.py --demo` → 출력 주소로 `curl "<주소의 /api/state?k=...>"` → `"demo": true`, `"lid_events"` 2개
- [ ] **Step 6: Commit** — `feat: bridge app and api`

### Task 6: 휴대폰 화면 `web/`

**Files:**
- Create: `pillbox/web/index.html`, `pillbox/web/style.css`, `pillbox/web/app.js`

**Interfaces:**
- Consumes: `GET /api/state`, `GET /api/history?days=35`, `POST /api/settings`, `POST /api/ack` (Task 5). 접속 코드는 `new URLSearchParams(location.search).get("k")`를 모든 요청에 붙임
- 화면 구성·기호·색 토큰·문구는 `docs/wiring/pill-mockup.html`을 출발점으로 한다. 시안의 연습 데이터, 상황 선택 상자, 내장 `judge()`는 지우고 API 값만 그린다
- 2초 조회. "자동 갱신 멈춤"이면 조회 중지. 조회 실패(네트워크) → "PC 프로그램에 연결할 수 없어요", 403 → "접속 주소를 다시 확인해 주세요", `board.connected=false` 또는 alert `unknown` → "상자 상태를 알 수 없어요"
- `demo:true`면 맨 위 "연습 데이터" 띠
- 설정 저장 실패(400) 시 입력란 아래 `aria-describedby`로 연결된 오류 문장
- 매초 바뀌는 "N초 전 수신"은 라이브 영역에 넣지 않음. 상태가 바뀔 때만 `role="status"` 문구 갱신, 경고 진입 시에만 `role="alert"`

- [ ] **Step 1: 화면 작성** (시안에서 옮기고 API 연결)
- [ ] **Step 2: 데모로 확인** — `py -3.12 pc/bridge.py --demo` 실행, PC 브라우저와 같은 Wi‑Fi 휴대폰에서 주소 열기. 확인: 경고 띠, 타임라인 ▲ 2개, 달력 오늘 칸, "확인했어요" → ◆ 표시와 소리 멈춤, 복용 시각 `25:00` 입력 → 오류 문장, `k` 지운 주소 → 403 문구, 프로그램 종료 → PC 끊김 문구
- [ ] **Step 3: Commit** — `feat: phone dashboard`

### Task 7: 통합·표준 검사와 README

**Files:**
- Create: `pillbox/README.md`, `pillbox/notes/check-results.md`

**Interfaces:**
- Consumes: 전체

- [ ] **Step 1: 실물 통합** — 배선(설계 2장) → 업로드 → `bridge.py --port COMx` → 휴대폰 접속. 설정에서 복용 시각을 지금+1분으로 저장하고 확인: 1분 후 `TAKE MEDICINE`, +30분 주의는 시각을 지금−31분으로 바꿔 즉시 확인, 버튼 → 2초 안에 "확인됨"과 초록 LED, USB 뽑기 → 회색 띠와 10초 뒤 `PC LOST`
- [ ] **Step 2: 표준 검사 기록** — `check-results.md`에 항목별 방법·결과·증거(수치, 캡처 파일명): 색 쌍 대비(라이트·다크), 키보드만 조작, 초점 가림, 버튼 크기, 흑백 캡처, TalkBack 또는 NVDA 낭독, 가족 역할 1명 3초 과업. 하지 못한 항목은 "미검사"로 적음
- [ ] **Step 3: README** — 준비물, 배선 그림 링크, 업로드, `py -3.12 -m venv .venv` → `pip install -r pc/requirements.txt` → 실행, 접속 주소, `--demo`, 알림 한계(페이지 열림 동안만), "의료기기 아님", 실물 확인과 연습 확인의 구분
- [ ] **Step 4: Commit** — `docs: readme and check results`
