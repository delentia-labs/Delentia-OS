"""
Round 57: turn "every weekday at 8:30", "ทุกวันจันทร์ 9 โมงเช้า", "in 20 minutes" or a cron line into a schedule, and say when it runs next.

Deterministic and model-free on purpose: a schedule decides when an unattended agent acts, so the same text must always mean the same thing and the
meaning must be shown to the person before it is saved (`describe`, `upcoming`). A text that is not understood is REFUSED with the forms that are
understood, never guessed. Supported:

  interval   every 30 minutes | every 2 hours | every day | hourly | daily | weekly | ทุก 30 นาที | ทุกชั่วโมง | ทุก 2 วัน
  daily/week every day at 9am | daily at 09:30 | every weekday at 8:30 | every monday at 10am | every mon,wed,fri at 18:00 | weekly on friday at 17:00
             ทุกวัน 09:00 | ทุกวันจันทร์ 9 โมงเช้า | ทุกวันทำงาน 8:30 | ทุกสัปดาห์วันศุกร์ 5 โมงเย็น
  monthly    monthly on the 1st at 9am | on the 15th of every month at 18:00 | ทุกวันที่ 1 ของเดือน 9 โมง
  once       in 20 minutes | at 14:30 | tomorrow at 9am | today at 5pm | on 2026-10-05 at 09:00 | อีก 20 นาที | พรุ่งนี้ 9 โมง | วันนี้ บ่าย 3 โมง
  cron       five fields: minute hour day-of-month month day-of-week (lists, ranges, steps, names), e.g.  */15 8-18 * * mon-fri

Thai clock words: "9 โมง" 09:00 (โมงเช้า), "บ่าย 2 โมง" 14:00, "4 โมงเย็น" 16:00, "ตี 5" 05:00, "2 ทุ่ม" 20:00, "เที่ยง" 12:00, "เที่ยงคืน" 00:00.
The shortest interval is 60 seconds (a recurring job that wakes a model every few seconds is a cost accident, not a schedule). Time zone: DELENTIA_TIMEZONE
(an IANA name such as Asia/Bangkok), else this machine's local zone; the zone is stored with the schedule so a moved host does not shift it.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, List, Optional, Set, Tuple

MIN_INTERVAL_S = 60
SEARCH_DAYS = 800                         # far enough for "29 February" style cron lines and months with no 31st

_DAYS = {"mon": 1, "monday": 1, "tue": 2, "tues": 2, "tuesday": 2, "wed": 3, "wednesday": 3, "thu": 4, "thur": 4, "thurs": 4, "thursday": 4,
         "fri": 5, "friday": 5, "sat": 6, "saturday": 6, "sun": 0, "sunday": 0}
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
_THAI_DAYS = [("อาทิตย์", 0), ("จันทร์", 1), ("อังคาร", 2), ("พุธ", 3), ("พฤหัสบดี", 4), ("พฤหัส", 4), ("ศุกร์", 5), ("เสาร์", 6)]
_UNIT_S = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600, "day": 86400, "week": 604800}
_THAI_UNIT_S = {"วินาที": 1, "นาที": 60, "ชั่วโมง": 3600, "ชม.": 3600, "วัน": 86400, "สัปดาห์": 604800, "อาทิตย์": 604800}

FORMS = ("every 30 minutes", "every day at 9am", "every weekday at 8:30", "every monday at 10am", "monthly on the 1st at 9am", "in 20 minutes",
         "tomorrow at 9am", "*/15 8-18 * * mon-fri", "ทุก 30 นาที", "ทุกวัน 09:00", "ทุกวันจันทร์ 9 โมงเช้า", "พรุ่งนี้ 9 โมง", "อีก 20 นาที")


class ScheduleError(ValueError):
    pass


def default_timezone_name() -> str:
    return (os.environ.get("DELENTIA_TIMEZONE") or "").strip()


def _tz(name: str) -> tzinfo:
    if name:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name)
        except Exception as exc:                                  # noqa: BLE001 - unknown zone or no tz database on this machine
            raise ScheduleError(f"unknown time zone {name!r} (use an IANA name such as Asia/Bangkok; on Windows `pip install tzdata`)") from exc
    return datetime.now().astimezone().tzinfo or timezone.utc


@dataclass
class Schedule:
    kind: str                                  # interval | cron | once
    text: str
    tz: str = ""
    interval_s: int = 0
    minutes: Set[int] = field(default_factory=set)
    hours: Set[int] = field(default_factory=set)
    dom: Set[int] = field(default_factory=set)
    months: Set[int] = field(default_factory=set)
    dow: Set[int] = field(default_factory=set)
    dom_any: bool = True
    dow_any: bool = True
    run_at: float = 0.0
    anchor: float = 0.0                        # intervals count from here (creation time)

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "text": self.text, "tz": self.tz, "interval_s": self.interval_s, "minutes": sorted(self.minutes), "hours": sorted(self.hours),
                "dom": sorted(self.dom), "months": sorted(self.months), "dow": sorted(self.dow), "dom_any": self.dom_any, "dow_any": self.dow_any,
                "run_at": self.run_at, "anchor": self.anchor}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Schedule":
        return Schedule(kind=data["kind"], text=data.get("text", ""), tz=data.get("tz", ""), interval_s=int(data.get("interval_s", 0)),
                        minutes=set(data.get("minutes", [])), hours=set(data.get("hours", [])), dom=set(data.get("dom", [])),
                        months=set(data.get("months", [])), dow=set(data.get("dow", [])), dom_any=bool(data.get("dom_any", True)),
                        dow_any=bool(data.get("dow_any", True)), run_at=float(data.get("run_at", 0.0)), anchor=float(data.get("anchor", 0.0)))


# ------------------------------------------------------------------ cron fields

def _field(text: str, low: int, high: int, names: Optional[Dict[str, int]] = None, wrap7: bool = False) -> Tuple[Set[int], bool]:
    """(values, was_a_bare_star). Lists, ranges, steps (*/5, 1-10/2) and names."""
    values: Set[int] = set()
    bare = text.strip() == "*"
    for part in text.split(","):
        part = part.strip().lower()
        if not part:
            raise ScheduleError(f"empty item in cron field {text!r}")
        step = 1
        if "/" in part:
            part, _, raw_step = part.partition("/")
            if not raw_step.isdigit() or int(raw_step) < 1:
                raise ScheduleError(f"bad step in {text!r}")
            step = int(raw_step)
        if part == "*":
            start, end = low, high
        elif "-" in part:
            a, _, b = part.partition("-")
            start, end = _num(a, names), _num(b, names)
            if wrap7 and end == 0 and start > 0:
                end = 7
        else:
            start = _num(part, names)
            end = high if step > 1 else start
        if start > end:
            raise ScheduleError(f"range {part!r} runs backwards")
        for v in range(start, end + 1, step):
            if wrap7 and v == 7:
                v = 0
            if not low <= v <= high:
                raise ScheduleError(f"{v} is outside {low}-{high} in {text!r}")
            values.add(v)
    return values, bare


def _num(token: str, names: Optional[Dict[str, int]]) -> int:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    if names and token in names:
        return names[token]
    raise ScheduleError(f"cannot read {token!r} in a cron field")


def parse_cron(text: str, tz: str = "") -> Schedule:
    fields = text.split()
    if len(fields) != 5:
        raise ScheduleError("a cron line has five fields: minute hour day-of-month month day-of-week")
    minutes, _ = _field(fields[0], 0, 59)
    hours, _ = _field(fields[1], 0, 23)
    dom, dom_any = _field(fields[2], 1, 31)
    months, _ = _field(fields[3], 1, 12, _MONTHS)
    dow, dow_any = _field(fields[4], 0, 6, _DAYS, wrap7=True)
    return Schedule("cron", text, tz, minutes=minutes, hours=hours, dom=dom, months=months, dow=dow, dom_any=dom_any, dow_any=dow_any)


# ------------------------------------------------------------------ clock times

def _hm(text: str) -> Optional[Tuple[int, int]]:
    """A time of day inside `text`, English or Thai. None if there is none."""
    t = text.lower()
    if re.search(r"เที่ยงคืน|midnight", t):
        return 0, 0
    if re.search(r"เที่ยง(?!คืน)|\bnoon\b", t):
        return 12, 0
    m = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)?", t)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
        return _ampm(h, ap), mi
    m = re.search(r"\b(\d{1,2})\s*(am|pm)\b", t)
    if m:
        return _ampm(int(m.group(1)), m.group(2)), 0
    m = re.search(r"ตี\s*(\d{1,2})", t)
    if m:
        return int(m.group(1)) % 24, 0
    m = re.search(r"(\d{1,2})\s*ทุ่ม", t)
    if m:
        return (18 + int(m.group(1))) % 24, 0
    m = re.search(r"(?:บ่าย\s*(\d{1,2})\s*โมง)|(?:(\d{1,2})\s*โมง\s*เย็น)|(?:เย็น\s*(\d{1,2})\s*โมง)", t)
    if m:
        h = int(next(g for g in m.groups() if g))
        return (h + 12) % 24 if h < 12 else h, 0
    m = re.search(r"(\d{1,2})\s*โมง", t)
    if m:
        h = int(m.group(1))
        return (h if h <= 12 else h) % 24, 0                      # "9 โมง", "9 โมงเช้า" = 09:00; a bare "7 โมง" is the morning
    return None


def _ampm(hour: int, ap: Optional[str]) -> int:
    if ap == "pm" and hour < 12:
        hour += 12
    if ap == "am" and hour == 12:
        hour = 0
    if not 0 <= hour <= 23:
        raise ScheduleError(f"{hour} is not an hour of the day")
    return hour


def _weekdays(text: str) -> Optional[Set[int]]:
    t = text.lower()
    if re.search(r"weekdays?|วันทำงาน|วันธรรมดา", t):
        return {1, 2, 3, 4, 5}
    if re.search(r"weekends?|เสาร์อาทิตย์|วันหยุดสุดสัปดาห์", t):
        return {0, 6}
    found: Set[int] = set()
    for word in re.findall(r"[a-z]+", t):
        if word in _DAYS:
            found.add(_DAYS[word])
    for name, number in _THAI_DAYS:
        if name in t:
            found.add(number)
    if "พฤหัสบดี" in t:
        found.add(4)
    return found or None


# ------------------------------------------------------------------ the parser

def parse(text: str, now: Optional[float] = None, tz: str = "") -> Schedule:
    """The schedule a piece of text means, or ScheduleError naming what is understood."""
    original = " ".join(str(text or "").split())
    if not original:
        raise ScheduleError("an empty schedule")
    if len(original) > 200:
        raise ScheduleError("a schedule is one short sentence or one cron line")
    zone = tz or default_timezone_name()
    _tz(zone)                                                      # validates the name now, not at the first run
    when = time.time() if now is None else float(now)
    t = original.lower()

    fields = t.split()
    if len(fields) == 5 and re.search(r"[\d*]", fields[0]) and all(re.fullmatch(r"[\d*/,\-a-z]+", f) for f in fields):
        return parse_cron(t, zone)

    clock = _hm(t)

    # ---- once
    m = re.fullmatch(r"(?:in|อีก)\s*(\d+)\s*(second|sec|minute|min|hour|hr|day|week|นาที|ชั่วโมง|ชม\.|วัน|สัปดาห์)s?", t)
    if m:
        unit = _UNIT_S.get(m.group(2)) or _THAI_UNIT_S[m.group(2)]
        seconds = int(m.group(1)) * unit
        if seconds < MIN_INTERVAL_S:
            raise ScheduleError(f"{seconds} s is below the {MIN_INTERVAL_S} s minimum")
        return Schedule("once", original, zone, run_at=when + seconds)
    if re.search(r"\b(tomorrow|today|tonight)\b|พรุ่งนี้|วันนี้|คืนนี้|^at\b|^on\s+\d{4}-\d{2}-\d{2}|^\d{4}-\d{2}-\d{2}", t) and not re.search(r"\bevery\b|ทุก", t):
        if clock is None:
            raise ScheduleError("a one-off schedule needs a time of day, e.g. 'tomorrow at 9am' or 'พรุ่งนี้ 9 โมง'")
        zone_info = _tz(zone)
        base = datetime.fromtimestamp(when, zone_info)
        day = base.date()
        iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
        if iso:
            try:
                day = datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))).date()
            except ValueError as exc:
                raise ScheduleError(f"{iso.group(0)} is not a date") from exc
        elif re.search(r"tomorrow|พรุ่งนี้", t):
            day = (base + timedelta(days=1)).date()
        target = datetime(day.year, day.month, day.day, clock[0], clock[1], tzinfo=zone_info)
        if target.timestamp() <= when:
            if not iso and not re.search(r"tomorrow|พรุ่งนี้", t) and not re.search(r"today|วันนี้|tonight|คืนนี้", t):
                target += timedelta(days=1)                      # "at 9am" when it is already 10am means tomorrow
            else:
                raise ScheduleError(f"{original!r} is already in the past")
        return Schedule("once", original, zone, run_at=target.timestamp())

    # ---- recurring
    m = re.fullmatch(r"(?:every|ทุก)\s*(\d+)\s*(second|sec|minute|min|hour|hr|day|week|นาที|ชั่วโมง|ชม\.|วัน|สัปดาห์)s?", t)
    if m:
        seconds = int(m.group(1)) * (_UNIT_S.get(m.group(2)) or _THAI_UNIT_S[m.group(2)])
        if seconds < MIN_INTERVAL_S:
            raise ScheduleError(f"every {seconds} s is below the {MIN_INTERVAL_S} s minimum")
        return Schedule("interval", original, zone, interval_s=seconds, anchor=when)
    # Bare interval words count from the moment the job is created. They never mean "at midnight" or "at 9": a time of day is never guessed.
    simple = {"hourly": 3600, "every hour": 3600, "ทุกชั่วโมง": 3600, "every minute": 60, "ทุกนาที": 60,
              "daily": 86400, "every day": 86400, "ทุกวัน": 86400, "nightly": 86400, "weekly": 604800, "every week": 604800,
              "ทุกสัปดาห์": 604800, "ทุกอาทิตย์": 604800}
    if t in simple:
        return Schedule("interval", original, zone, interval_s=simple[t], anchor=when)
    if t in ("monthly", "every month", "ทุกเดือน"):
        raise ScheduleError("name the day and the time, e.g. 'monthly on the 1st at 9am' (a day of the month is never guessed)")

    if re.search(r"\bmonthly\b|every month|of every month|ของเดือน|ทุกเดือน", t) or re.search(r"\bon the \d{1,2}(st|nd|rd|th)\b", t):
        dom_match = re.search(r"(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b|วันที่\s*(\d{1,2})", t)
        if dom_match is None or clock is None:
            raise ScheduleError("a monthly schedule names the day and the time, e.g. 'monthly on the 1st at 9am' or 'ทุกวันที่ 1 ของเดือน 9 โมง' (neither is guessed)")
        number = int(next(g for g in dom_match.groups() if g))
        if not 1 <= number <= 31:
            raise ScheduleError(f"{number} is not a day of the month")
        return _monthly(original, zone, {number}, clock)

    days = _weekdays(t)
    if re.search(r"\bevery\b|\bdaily\b|\bweekly\b|ทุก|\bweekdays?\b|\bweekends?\b|วันทำงาน|วันธรรมดา", t):
        if days is None and not re.search(r"day|วัน|daily", t):
            raise ScheduleError(f"I could not read {original!r}")
        if clock is None:
            raise ScheduleError("name a time of day, e.g. 'every day at 9am' or 'ทุกวัน 09:00' (the default is not guessed)")
        return Schedule("cron", original, zone, minutes={clock[1]}, hours={clock[0]}, dom=set(range(1, 32)), months=set(range(1, 13)),
                        dow=days if days is not None else set(range(7)), dom_any=True, dow_any=days is None)
    raise ScheduleError(f"I could not read {original!r}. Understood forms: " + "; ".join(FORMS))


def _monthly(text: str, zone: str, days: Set[int], at: Tuple[int, int]) -> Schedule:
    return Schedule("cron", text, zone, minutes={at[1]}, hours={at[0]}, dom=days, months=set(range(1, 13)), dow=set(range(7)), dom_any=False, dow_any=True)


# ------------------------------------------------------------------ when does it run next

def next_run(schedule: Schedule, after: float) -> Optional[float]:
    """The first run strictly after `after` (epoch seconds), or None when a one-off is over."""
    if schedule.kind == "once":
        return schedule.run_at if schedule.run_at > after else None
    if schedule.kind == "interval":
        step = schedule.interval_s
        if step < MIN_INTERVAL_S:
            raise ScheduleError(f"interval {step} s is below the {MIN_INTERVAL_S} s minimum")
        anchor = schedule.anchor or after
        if after < anchor:
            return anchor + step
        return anchor + (int((after - anchor) // step) + 1) * step
    zone = _tz(schedule.tz)
    start = datetime.fromtimestamp(after, zone).replace(second=0, microsecond=0) + timedelta(minutes=1)
    day = start.date()
    for offset in range(SEARCH_DAYS):
        current = day + timedelta(days=offset)
        if current.month not in schedule.months:
            continue
        dom_ok = current.day in schedule.dom
        dow_ok = ((current.weekday() + 1) % 7) in schedule.dow          # Python: Monday 0; cron: Sunday 0
        if schedule.dom_any and schedule.dow_any:
            ok = True
        elif schedule.dom_any:
            ok = dow_ok
        elif schedule.dow_any:
            ok = dom_ok
        else:
            ok = dom_ok or dow_ok                                      # classic cron: both restricted means either
        if not ok:
            continue
        for hour in sorted(schedule.hours):
            for minute in sorted(schedule.minutes):
                candidate = datetime(current.year, current.month, current.day, hour, minute, tzinfo=zone)
                if candidate >= start:
                    return candidate.timestamp()
    return None


def upcoming(schedule: Schedule, after: float, count: int = 5) -> List[float]:
    out: List[float] = []
    cursor = after
    for _ in range(count):
        nxt = next_run(schedule, cursor)
        if nxt is None:
            break
        out.append(nxt)
        cursor = nxt
    return out


def describe(schedule: Schedule) -> str:
    """One plain sentence for what was understood, shown before anything is saved."""
    if schedule.kind == "once":
        return "once, at " + datetime.fromtimestamp(schedule.run_at, _tz(schedule.tz)).strftime("%Y-%m-%d %H:%M %Z")
    if schedule.kind == "interval":
        s = schedule.interval_s
        for unit, size in (("week", 604800), ("day", 86400), ("hour", 3600), ("minute", 60)):
            if s % size == 0:
                n = s // size
                return f"every {n} {unit}{'s' if n != 1 else ''}"
        return f"every {s} seconds"
    names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    times = ", ".join(f"{h:02d}:{m:02d}" for h in sorted(schedule.hours) for m in sorted(schedule.minutes))
    if len(schedule.hours) * len(schedule.minutes) > 6:
        times = f"{len(schedule.hours) * len(schedule.minutes)} times a day (from {min(schedule.hours):02d}:{min(schedule.minutes):02d})"
    where = ""
    if not schedule.dom_any:
        where = " on day " + ",".join(str(d) for d in sorted(schedule.dom)) + " of the month"
    elif not schedule.dow_any:
        where = " on " + ",".join(names[d] for d in sorted(schedule.dow))
    if len(schedule.months) < 12:
        where += " in months " + ",".join(str(m) for m in sorted(schedule.months))
    return f"at {times}{where or ' every day'} ({schedule.tz or 'local time'})"
