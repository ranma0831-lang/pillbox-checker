# 약 복용 확인 상자 (pillbox-checker)

혼자 지내며 매일 약을 드시는 분이 상자 뚜껑을 열고 버튼을 누르면, 떨어져 사는 가족이 같은 Wi-Fi의 휴대폰에서 "오늘 드셨는지"를 바로 확인하는 작품입니다. Arduino UNO, PC 프로그램(Python), 휴대폰 웹 화면으로 이루어져 있습니다.

> 의료기기가 아닌 시연용 포트폴리오 작품입니다.

## 한눈에 보기

| 구성 | 하는 일 |
|---|---|
| 상자 (UNO) | 뚜껑 열림(기울기 스위치)과 "먹었어요" 버튼을 읽고, 빨강·초록 LED와 LCD로 현장에 알림 |
| PC 프로그램 | 복용 여부 판정, 90일 기록, 상자에 LED·LCD 명령 전송, 휴대폰 화면 제공 |
| 휴대폰 화면 | 오늘 상태, 하루 타임라인, 월 달력, 최근 14일 그래프, 미복용 알림 |

```
[UNO 상자] ⇄ USB 115200 JSON ⇄ [PC: bridge.py] ⇄ 같은 Wi-Fi ⇄ [가족 휴대폰]
```

## 동작 규칙

- **확인 인정:** 복용 시각 2시간 전부터 그날 자정까지 누른 첫 버튼. 더 일찍 누르면 "인정 전 누름"으로 기록만 함
- **상자 알림:** 복용 시각 +3분부터 빨강 LED가 버튼을 누를 때까지 깜빡임. 누르면 초록 LED가 10초 켜짐
- **휴대폰 알림:** +30분 주의(노랑), +60분 경고(빨강·소리·진동). 가족이 "확인했어요"를 누르면 기록
- **뚜껑 열림은 판정에 쓰지 않음:** 열었다고 먹은 것은 아니므로 화면에서 "뚜껑 열림"과 "본인 확인"을 구분해 표시
- **LCD 화면 5가지:** 다음 복용 / 복용 시간 / 복용 지남 / 완료(확인 시각) / PC 연결 끊김

## 준비물과 배선

SZH-EK013 아두이노 고급키트: UNO 호환 R3, 빵판, 빨강·초록 LED, 1kΩ 2개, 택트 스위치, 볼 기울기 스위치, LCD1602 I2C, 점퍼선 16개.

| UNO 핀 | 부품 |
|---|---|
| D8 / D9 | 빨강 / 초록 LED (각 1kΩ) |
| D2 | 택트 스위치 (INPUT_PULLUP) |
| D3 | 볼 기울기 스위치 (뚜껑 안쪽) |
| A4 / A5 | LCD SDA / SCL |

한 선씩 따라 하는 배선도: [배선도 페이지](https://ranma0831-lang.github.io/pillbox-checker/wiring/index.html#pill) (저장소의 `docs/wiring/index.html`, F 탭). 보드 없이 보는 [휴대폰 화면 시안](https://ranma0831-lang.github.io/pillbox-checker/wiring/pill-mockup.html). 택트 스위치는 다리 방향을 확인해서 꽂아야 합니다. 90° 돌아가면 늘 눌린 상태로 읽힙니다.

## 실행

```powershell
# 1) 펌웨어 업로드 (포트는 arduino-cli board list 로 확인)
arduino-cli lib install "hd44780@1.3.2"
arduino-cli upload -p COM5 --fqbn arduino:avr:uno firmware/pillbox

# 2) PC 프로그램
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r pc\requirements.txt
.venv\Scripts\python.exe pc\bridge.py --port COM5

# 보드 없이 연습 데이터로 보기
.venv\Scripts\python.exe pc\bridge.py --demo
```

콘솔에 나오는 `http://192.168.x.x:8000/?k=123456` 주소를 같은 Wi-Fi 휴대폰에서 엽니다. 접속 코드는 실행할 때마다 바뀌며, 코드가 없으면 데이터를 볼 수 없습니다.

## 접근성과 표준

ISO 9241-110·-11과 WCAG 2.2를 기준으로 설계했습니다. 상태를 색만이 아니라 기호(✓ ! ✕)와 문장으로 함께 표시하고(1.4.1), 그래프 내용을 표로도 제공하며(1.1.1), 키보드 조작(2.1.1), 48px 버튼(2.5.8), 상태 메시지 낭독(4.1.3), 경고음 끄기(1.4.2), 자동 갱신 멈춤(2.2.2)을 넣었습니다. 글자 색 대비는 라이트·다크 모두 4.5:1 이상으로 계산했습니다. 검사한 항목과 아직 검사하지 않은 항목은 [`notes/check-results.md`](notes/check-results.md)에 구분해 두었습니다.

## 확인 상태

- 자동 테스트 38개 통과: `.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py"`
- 실물 보드·휴대폰에서 확인: 버튼 → LED·LCD → 휴대폰 갱신, USB 뽑기·PC 종료 시 문구와 자동 재연결, 접속 코드 거절
- 아직 하지 않음: 스크린리더 낭독, 키보드만으로 조작, 사용자 3초 과업 테스트

## 한계

- 알림은 휴대폰에서 페이지가 열려 있을 때만 울립니다(같은 Wi-Fi의 http 주소라 푸시 알림 불가).
- 상자에는 시계가 없어 날짜·시각은 PC 기준입니다. PC가 꺼진 날은 "기록 없음"입니다.
- 아침 복용 시각을 전제로 합니다. 자정 근처나 저녁 시각은 판정과 그래프 축이 맞지 않을 수 있습니다.

## 폴더

| 경로 | 내용 |
|---|---|
| `firmware/pillbox/` | UNO 펌웨어 |
| `pc/` | 판정(`judge.py`), 기록(`store.py`), 시리얼(`serial_link.py`), PC 프로그램(`bridge.py`)과 테스트 |
| `web/` | 휴대폰 화면 |
| `docs/` | 설계 문서, 구현 계획, 배선도, 화면 시안 |
| `notes/` | 펌웨어 점검표, 확인 결과 |
