# 약 복용 확인 상자

뚜껑 열림과 "먹었어요" 버튼을 UNO가 읽고, PC 프로그램이 복용 여부를 판정·기록해 같은 Wi-Fi의 가족 휴대폰 화면에 보여 주는 포트폴리오 작품입니다. **의료기기가 아닌 시연용 작품입니다.**

- 설계: `../docs/superpowers/specs/2026-10-29-pillbox-design.md`
- 배선도 (한 선씩 보기): `../service-options/index.html`의 F 탭

## 준비물

SZH-EK013 고급키트의 UNO 호환 R3, USB 케이블, 빵판, 빨강·초록 LED, 1kΩ 저항 2개, 택트 스위치, 볼 기울기 스위치, LCD1602 I2C, 점퍼선. PC(Windows, Python 3.12, arduino-cli)와 같은 Wi-Fi의 휴대폰.

| UNO 핀 | 부품 |
|---|---|
| D8 | 빨강 LED + 1kΩ (복용 알림) |
| D9 | 초록 LED + 1kΩ (오늘 확인됨) |
| D2 | 택트 스위치 (반대편 GND) |
| D3 | 볼 기울기 스위치 (반대편 GND, 뚜껑 안쪽) |
| A4 / A5 | LCD SDA / SCL |

## 순서

1. **USB를 뺀 상태로** 배선도대로 16개 선을 연결합니다.
2. USB를 꽂고 `arduino-cli board list`로 새로 생긴 포트를 찾습니다(뽑기 전후 비교).
3. 업로드:
   ```
   arduino-cli lib install "hd44780@1.3.2"
   arduino-cli upload -p COM5 --fqbn arduino:avr:uno firmware/pillbox
   ```
   (처음이면 먼저 `arduino-cli compile --fqbn arduino:avr:uno firmware/pillbox`)
4. Arduino 시리얼 모니터로 `notes/firmware-check.md` 항목을 확인하고, 시리얼 모니터를 **닫습니다**(포트를 하나의 프로그램만 쓸 수 있음).
5. PC 프로그램:
   ```
   py -3.12 -m venv .venv
   .venv\Scripts\python.exe -m pip install -r pc\requirements.txt
   .venv\Scripts\python.exe pc\bridge.py --port COM5
   ```
6. 콘솔에 나온 `http://192.168.x.x:8000/?k=123456` 주소를 같은 Wi-Fi 휴대폰에서 엽니다. 이 주소는 실행할 때마다 바뀌며, 가족에게만 보냅니다.
7. 휴대폰에서 "알림 소리 켜기"를 한 번 누릅니다.

Windows 방화벽이 Python의 네트워크 접근을 물으면 **개인 네트워크**만 허용합니다.

## 보드 없이 보기

```
.venv\Scripts\python.exe pc\bridge.py --demo
```

지난 30일 연습 기록과 "뚜껑만 열고 확인 안 함(경고)" 장면을 만듭니다. 화면 맨 위에 "연습 데이터" 띠가 표시되고, 실제 기록(`pc/records.jsonl`)과 섞이지 않습니다.

## 판정 규칙

- 복용 시각 2시간 전부터 그날 자정까지 누른 첫 버튼을 확인으로 인정합니다. 그 전에 누르면 "인정 전 누름"으로 기록만 합니다.
- 복용 시각 +30분까지 확인 없으면 주의, +60분이면 경고(빨강 LED 깜빡임, 휴대폰 소리·진동).
- 뚜껑 열림은 기록과 화면 표시에만 쓰고 판정에 쓰지 않습니다.
- 기록은 90일 보관합니다.

## 한계

- 알림은 휴대폰에서 **페이지가 열려 있을 때만** 울립니다(같은 Wi-Fi의 http 주소에서는 푸시 알림을 쓸 수 없음).
- 날짜·시각은 PC 기준입니다. PC가 꺼져 있던 날은 "기록 없음"입니다.
- 실물로 확인한 항목과 연습 데이터로만 확인한 항목은 `notes/check-results.md`에서 구분합니다.

## 테스트

```
.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py"
```
