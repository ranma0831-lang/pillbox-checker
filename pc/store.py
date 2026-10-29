"""기록(records.jsonl)과 설정(settings.json)."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from pc.judge import parse_hhmm

DEFAULT_SETTINGS = {"dose_time": "08:00", "grace_min": 30}
PRESS_EVENTS = ("press", "early_press")  # 복용 시각이 바뀌면 둘 다 다시 판정해야 함


def append(path: Path, event, t, **extra):
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"t": t.strftime("%Y-%m-%dT%H:%M:%S"), "e": event, **extra}, ensure_ascii=False) + "\n")


def load(path: Path, now, keep_days=90):
    path = Path(path)
    if not path.exists():
        return []
    cutoff = now - timedelta(days=keep_days)
    keep, dropped = [], False
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            r = json.loads(line)
            r["_dt"] = datetime.fromisoformat(r["t"])
        except (ValueError, KeyError, TypeError):
            print(f"경고: {path.name} {n}번째 줄이 깨져 건너뜁니다", file=sys.stderr)
            continue
        if r["_dt"] < cutoff:
            dropped = True
            continue
        keep.append(r)
    if dropped:
        path.write_text("".join(json.dumps({k: v for k, v in r.items() if k != "_dt"}, ensure_ascii=False) + "\n" for r in keep), encoding="utf-8")
    return keep


def presses_by_day(records):
    out = {}
    for r in records:
        if r["e"] in PRESS_EVENTS:
            out.setdefault(r["_dt"].date(), []).append(r["_dt"].hour * 60 + r["_dt"].minute)
    return {d: sorted(v) for d, v in out.items()}


def days_with_records(records):
    return {r["_dt"].date() for r in records}


def load_settings(path: Path):
    try:
        return {**DEFAULT_SETTINGS, **json.loads(Path(path).read_text(encoding="utf-8"))}
    except (FileNotFoundError, ValueError):
        return dict(DEFAULT_SETTINGS)


def save_settings(path: Path, dose_time):
    parse_hhmm(dose_time)
    s = {**load_settings(path), "dose_time": dose_time}
    Path(path).write_text(json.dumps(s), encoding="utf-8")
    return s
