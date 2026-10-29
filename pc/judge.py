"""복용 판정 규칙. 시각은 모두 자정 기준 분(int)."""
import re

WINDOW_BEFORE = 120  # 복용 시각 2시간 전부터 확인 인정
WARN_AFTER = 60
REMIND_AFTER = 3  # 상자 빨강 LED는 복용 시각 3분 뒤부터 깜빡임

_OUT = {  # REMIND, DONE, WINDOW, MSG (LCD: 0 다음 복용, 1 복용 시간, 2 완료, 3 PC 끊김, 4 지남)
    "before": (0, 0, 0, 0), "window": (0, 0, 1, 0), "due": (0, 0, 1, 1),
    "caution": (1, 0, 1, 4), "warning": (1, 0, 1, 4),
    "done": (0, 1, 1, 2), "late": (0, 1, 1, 2),
}


def parse_hhmm(s):
    m = re.fullmatch(r"(\d{2}):(\d{2})", s or "")
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        raise ValueError(f"HH:MM 형식이 아닙니다: {s!r}")
    return int(m[1]) * 60 + int(m[2])


def judge(presses, dose, now, *, has_records=True, stale=False, grace=30):
    start = dose - WINDOW_BEFORE
    valid = [p for p in presses if p >= start]
    early = [p for p in presses if p < start]
    if valid:
        at = min(valid)
        return {"status": "late" if at > dose + grace else "done", "at": at, "early": early}
    if now is None:
        st = "missed" if has_records else "none"
    elif stale:
        st = "unknown"
    elif now < start:
        st = "before"
    elif now < dose:
        st = "window"
    elif now < dose + grace:
        st = "due"
    elif now < dose + WARN_AFTER:
        st = "caution"
    else:
        st = "warning"
    return {"status": st, "at": None, "early": early}


def outputs(status, now=None, dose=None):
    out = _OUT.get(status, (0, 0, 0, 0))
    if status == "due" and now is not None and dose is not None and now >= dose + REMIND_AFTER:
        out = (1, 0, 1, 4)
    return dict(zip(("REMIND", "DONE", "WINDOW", "MSG"), out))
