# 펌웨어 점검표 (시리얼 모니터 115200, 줄 끝 LF)

업로드: `arduino-cli upload -p COMx --fqbn arduino:avr:uno firmware/pillbox`
포트 확인: `arduino-cli board list` (USB를 뽑았다 꽂으면 새로 생기는 포트)

| 확인 | 보낼 것 / 할 일 | 기대 결과 | 결과 |
|---|---|---|---|
| LCD 연결 끊김 | I2C 시간 제한 추가 후 LCD 전원 없이 실행 | `lcd_ready:false`로 계속 동작 확인 (이전 펌웨어는 멈춤) |
| 프로파일 | `1 STATUS` | `"profile":"PILL"`, `"request":1` | 2026-10-29 COM5: `9 STATUS` → `"profile":"PILL","request":9` 확인 |
| 뚜껑 | 열고 닫기, 흔들기 | `lid_open`/`lid_close` 각 1회. 반대면 `LID_OPEN_LEVEL`을 LOW로 | 통과: 기울임 → lid_open, 세움 → lid_close (방향 수정 불필요) |
| 버튼 | 길게 눌렀다 떼기 | `press` 1회 | 통과(2026-10-29): 처음엔 버튼이 90° 돌아가 꽂혀 늘 눌림 → 방향을 바꿔 해결. 누를 때마다 `press` 기록 (5회 눌러 5회 기록, 떨림 없음) |
| 인정 전 | `2 WINDOW 0` 후 버튼 | 초록 두 번 깜빡임 | 미실시 |
| 인정 중 | `3 WINDOW 1` 후 버튼 | 초록 켜짐 유지 | 미실시 |
| 알림 | `4 REMIND 1` | 빨강 0.5초 깜빡임 | ACK 확인. 깜빡임은 눈으로 확인 필요 |
| LCD | `5 MSG 1` | `TAKE MEDICINE` | ACK 확인. LCD 글자는 눈으로 확인 필요 (`lcd_ready:true`) |
| 오류 | `6 FOO` | `"type":"error"` | `4 FOO`·`5 MSG 7` → bad_command, `abc` → bad_request 확인 |
| PC 끊김 | 10초 동안 아무것도 안 보냄 | LCD `PC LOST`, 빨강 멈춤 | 미실시 |

참고: 포트를 열면 UNO가 재시작하고, 그 전에 쌓인 줄이 반쯤 잘려 먼저 들어옵니다. PC 프로그램은 이런 줄을 버리도록 되어 있습니다.
