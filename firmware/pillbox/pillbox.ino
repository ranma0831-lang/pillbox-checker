// 약 복용 확인 상자 · UNO 호환 R3 · 115200 줄 단위 JSON
// 핀: 빨강 D8, 초록 D9, 버튼 D2, 기울기 D3, LCD I2C A4/A5. D0/D1은 USB 시리얼용으로 비움.
#include <Wire.h>
#include <hd44780.h>
#include <hd44780ioClass/hd44780_I2Cexp.h>

const byte PIN_RED = 8, PIN_GREEN = 9, PIN_BUTTON = 2, PIN_LID = 3;
// 실물에서 뚜껑을 열었을 때 읽히는 값. 시리얼로 확인 후 반대면 LOW로 바꾼다.
const byte LID_OPEN_LEVEL = HIGH;
const unsigned long LID_DEBOUNCE = 50, BUTTON_DEBOUNCE = 30, PC_TIMEOUT = 10000, GREEN_MS = 10000;

hd44780_I2Cexp lcd;
bool lcdReady = false;

byte remind = 0, done = 0, window = 0, msg = 0;
bool pcLost = false;
unsigned long lastCmd = 0, lastState = 0, blink2Start = 0, greenStart = 0;
bool blink2 = false, greenOn = false;  // 초록은 확인 버튼 뒤 10초만 켠다
int doseHHMM = -1, takenHHMM = -1;     // PC가 알려 주는 복용·확인 시각 (보드엔 시계가 없음)

bool lidOpen = false; byte lidRaw; unsigned long lidChanged = 0;
bool btnDown = false; byte btnRaw; unsigned long btnChanged = 0;

char buf[33]; byte len = 0; bool overflow = false;

// "08:00" 또는 "--:--"
void fmtTime(char* out, int hhmm) {
  if (hhmm < 0) strcpy(out, "--:--");
  else snprintf(out, 6, "%02d:%02d", hhmm / 100, hhmm % 100);
}

// LCD 화면: 0 다음 복용, 1 복용 시간, 2 완료, 3 PC 끊김, 4 복용 지남
void showMsg(byte m) {
  if (!lcdReady) return;
  char t[6], l1[17], l2[17];
  fmtTime(t, m == 2 ? takenHHMM : doseHHMM);
  switch (m) {
    case 0: strcpy(l1, "NEXT DOSE"); snprintf(l2, 17, "AT %s", t); break;
    case 1: strcpy(l1, "MEDICINE TIME!"); snprintf(l2, 17, "DOSE %s NOW", t); break;
    case 2: strcpy(l1, "DONE TODAY  :)");
            if (takenHHMM >= 0) snprintf(l2, 17, "TAKEN AT %s", t); else strcpy(l2, "WELL DONE"); break;
    case 3: strcpy(l1, "PC LOST"); strcpy(l2, "CHECK THE PC"); break;
    default: snprintf(l1, 17, "OVERDUE   %s", t); strcpy(l2, "PRESS BUTTON"); break;
  }
  lcd.clear();
  lcd.print(l1);
  lcd.setCursor(0, 1);
  lcd.print(l2);
}

void sendAck(long req) {
  Serial.print(F("{\"v\":1,\"type\":\"ack\",\"request\":")); Serial.print(req); Serial.println(F(",\"applied\":true}"));
}

void sendError(long req, const __FlashStringHelper* code) {
  Serial.print(F("{\"v\":1,\"type\":\"error\",\"request\":")); Serial.print(req);
  Serial.print(F(",\"code\":\"")); Serial.print(code); Serial.println(F("\"}"));
}

void sendEvent(const __FlashStringHelper* ev) {
  Serial.print(F("{\"v\":1,\"type\":\"event\",\"event\":\"")); Serial.print(ev);
  Serial.print(F("\",\"ms\":")); Serial.print(millis()); Serial.println('}');
}

void sendState(long req) {
  Serial.print(F("{\"v\":1,\"type\":\"state\",\"profile\":\"PILL\",\"request\":")); Serial.print(req);
  Serial.print(F(",\"ms\":")); Serial.print(millis());
  Serial.print(F(",\"lid_open\":")); Serial.print(lidOpen ? F("true") : F("false"));
  Serial.print(F(",\"button_pressed\":")); Serial.print(btnDown ? F("true") : F("false"));
  Serial.print(F(",\"remind\":")); Serial.print(remind);
  Serial.print(F(",\"done\":")); Serial.print(done);
  Serial.print(F(",\"msg\":")); Serial.print(msg);
  Serial.print(F(",\"lcd_ready\":")); Serial.print(lcdReady ? F("true") : F("false"));
  Serial.println('}');
}

// "요청번호 명령 [인수]"
void handleLine() {
  char* tok = strtok(buf, " ");
  long req = tok ? atol(tok) : 0;
  if (req < 1 || req > 65535) { sendError(0, F("bad_request")); return; }
  char* cmd = strtok(NULL, " ");
  char* arg = strtok(NULL, " ");
  long v = arg ? atol(arg) : -1;
  bool binArg = arg && (strcmp(arg, "0") == 0 || strcmp(arg, "1") == 0);

  lastCmd = millis();
  if (pcLost) { pcLost = false; showMsg(msg); }

  if (!cmd) { sendError(req, F("bad_command")); return; }
  if (strcmp(cmd, "PING") == 0) sendAck(req);
  else if (strcmp(cmd, "STATUS") == 0) sendState(req);
  else if (strcmp(cmd, "STOP") == 0) { remind = 0; done = 0; msg = 0; greenOn = false; showMsg(msg); sendAck(req); }
  else if (strcmp(cmd, "REMIND") == 0 && binArg) { remind = v; sendAck(req); }
  else if (strcmp(cmd, "DONE") == 0 && binArg) { done = v; sendAck(req); }
  else if (strcmp(cmd, "WINDOW") == 0 && binArg) { window = v; sendAck(req); }
  else if (strcmp(cmd, "MSG") == 0 && arg && v >= 0 && v <= 4 && strlen(arg) == 1) { msg = v; showMsg(msg); sendAck(req); }
  else if ((strcmp(cmd, "DOSE") == 0 || strcmp(cmd, "TAKEN") == 0) && arg && v >= -1 && v <= 2359 && (v < 0 || v % 100 < 60)) {
    if (cmd[0] == 'D') doseHHMM = v; else takenHHMM = v;
    if (!pcLost) showMsg(msg);
    sendAck(req);
  }
  else sendError(req, F("bad_command"));
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (overflow) sendError(0, F("bad_request"));
      else if (len) { buf[len] = 0; handleLine(); }
      len = 0; overflow = false;
    } else if (len < sizeof(buf) - 1) buf[len++] = c;
    else overflow = true;
  }
}

void readInputs(unsigned long now) {
  byte r = digitalRead(PIN_LID);
  if (r != lidRaw) { lidRaw = r; lidChanged = now; }
  bool open = (lidRaw == LID_OPEN_LEVEL);
  if (open != lidOpen && now - lidChanged >= LID_DEBOUNCE) {
    lidOpen = open;
    if (open) sendEvent(F("lid_open")); else sendEvent(F("lid_close"));
  }

  byte b = digitalRead(PIN_BUTTON);
  if (b != btnRaw) { btnRaw = b; btnChanged = now; }
  bool down = (btnRaw == LOW);
  if (down != btnDown && now - btnChanged >= BUTTON_DEBOUNCE) {
    btnDown = down;
    if (!down) {  // 뗄 때 한 번
      sendEvent(F("press"));
      if (window) {  // PC 응답 전에도 현장에서 바로 보이게
        if (!done) takenHHMM = -1;  // 그날 첫 확인일 때만. 두 번째 누름은 PC가 시각을 다시 보내지 않음
        done = 1; remind = 0; msg = 2;
        greenOn = true; greenStart = now;
        if (!pcLost) showMsg(msg);
      } else { blink2 = true; blink2Start = now; }
    }
  }
}

void updateOutputs(unsigned long now) {
  if (greenOn && now - greenStart >= GREEN_MS) greenOn = false;
  bool green = greenOn;
  if (blink2) {
    unsigned long t = now - blink2Start;
    if (t >= 600) blink2 = false;
    else green = (t / 150) % 2 == 0;  // 150ms 켜짐·꺼짐 두 번
  }
  digitalWrite(PIN_GREEN, green);
  digitalWrite(PIN_RED, remind && !pcLost && (now / 500) % 2 == 0);
}

void setup() {
  pinMode(PIN_RED, OUTPUT); pinMode(PIN_GREEN, OUTPUT);
  digitalWrite(PIN_RED, LOW); digitalWrite(PIN_GREEN, LOW);
  pinMode(PIN_BUTTON, INPUT_PULLUP); pinMode(PIN_LID, INPUT_PULLUP);
  Serial.begin(115200);
  // LCD 선이 빠지거나 전원이 없으면 I2C가 멈춰 상자 전체가 멈춘다. 시간 제한을 걸어 LCD 없이도 동작하게 한다.
  Wire.begin();
  Wire.setWireTimeout(25000, true);
  lcdReady = lcd.begin(16, 2) == 0;
  showMsg(0);
  lidRaw = digitalRead(PIN_LID); lidOpen = (lidRaw == LID_OPEN_LEVEL);
  btnRaw = digitalRead(PIN_BUTTON);
  lastCmd = millis();
}

void loop() {
  unsigned long now = millis();
  readSerial();
  readInputs(now);
  // readSerial 안에서 lastCmd가 now보다 커질 수 있으므로 millis()를 다시 읽는다
  if (!pcLost && millis() - lastCmd > PC_TIMEOUT) { pcLost = true; showMsg(3); }
  updateOutputs(now);
  if (now - lastState >= 1000) { lastState = now; sendState(0); }
}
