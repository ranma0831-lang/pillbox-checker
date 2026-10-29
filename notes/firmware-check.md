# 펌웨어 점검표 (시리얼 모니터 115200, 줄 끝 LF)

업로드: `arduino-cli upload -p COMx --fqbn arduino:avr:uno firmware/pillbox`
포트 확인: `arduino-cli board list` (USB를 뽑았다 꽂으면 새로 생기는 포트)

| 확인 | 보낼 것 / 할 일 | 기대 결과 | 결과 |
|---|---|---|---|
| 프로파일 | `1 STATUS` | `"profile":"PILL"`, `"request":1` | 미실시 |
| 뚜껑 | 열고 닫기, 흔들기 | `lid_open`/`lid_close` 각 1회. 반대면 `LID_OPEN_LEVEL`을 LOW로 | 미실시 |
| 버튼 | 길게 눌렀다 떼기 | `press` 1회 | 미실시 |
| 인정 전 | `2 WINDOW 0` 후 버튼 | 초록 두 번 깜빡임 | 미실시 |
| 인정 중 | `3 WINDOW 1` 후 버튼 | 초록 켜짐 유지 | 미실시 |
| 알림 | `4 REMIND 1` | 빨강 0.5초 깜빡임 | 미실시 |
| LCD | `5 MSG 1` | `TAKE MEDICINE` | 미실시 |
| 오류 | `6 FOO` | `"type":"error"` | 미실시 |
| PC 끊김 | 10초 동안 아무것도 안 보냄 | LCD `PC LOST`, 빨강 멈춤 | 미실시 |
