"""
Round 57: nl_schedule.py - what a schedule text means. Pure functions, no model; a fixed "now" (Saturday 2026-10-03 10:00, Asia/Bangkok) so every
expectation is a date a person can check on a calendar.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from rct_control_plane import nl_schedule as ns

ZONE = "Asia/Bangkok"
TZ = ZoneInfo(ZONE)
NOW = datetime(2026, 10, 3, 10, 0, tzinfo=TZ).timestamp()          # a Saturday


def at(text, count=3, now=NOW):
    s = ns.parse(text, now=now, tz=ZONE)
    return [datetime.fromtimestamp(t, TZ).strftime("%a %m-%d %H:%M") for t in ns.upcoming(s, now, count)]


@pytest.mark.parametrize("text,expected", [
    ("every 30 minutes", ["Sat 10-03 10:30", "Sat 10-03 11:00", "Sat 10-03 11:30"]),
    ("ทุก 30 นาที", ["Sat 10-03 10:30", "Sat 10-03 11:00", "Sat 10-03 11:30"]),
    ("every 2 hours", ["Sat 10-03 12:00", "Sat 10-03 14:00", "Sat 10-03 16:00"]),
    ("hourly", ["Sat 10-03 11:00", "Sat 10-03 12:00", "Sat 10-03 13:00"]),
    ("ทุกชั่วโมง", ["Sat 10-03 11:00", "Sat 10-03 12:00", "Sat 10-03 13:00"]),
    ("every day at 9am", ["Sun 10-04 09:00", "Mon 10-05 09:00", "Tue 10-06 09:00"]),
    ("daily at 09:30", ["Sun 10-04 09:30", "Mon 10-05 09:30", "Tue 10-06 09:30"]),
    ("ทุกวัน 09:00", ["Sun 10-04 09:00", "Mon 10-05 09:00", "Tue 10-06 09:00"]),
    ("every weekday at 8:30", ["Mon 10-05 08:30", "Tue 10-06 08:30", "Wed 10-07 08:30"]),
    ("ทุกวันทำงาน 8:30", ["Mon 10-05 08:30", "Tue 10-06 08:30", "Wed 10-07 08:30"]),
    ("every monday at 10am", ["Mon 10-05 10:00", "Mon 10-12 10:00", "Mon 10-19 10:00"]),
    ("ทุกวันจันทร์ 9 โมงเช้า", ["Mon 10-05 09:00", "Mon 10-12 09:00", "Mon 10-19 09:00"]),
    ("every mon,wed,fri at 6pm", ["Mon 10-05 18:00", "Wed 10-07 18:00", "Fri 10-09 18:00"]),
    ("weekly on friday at 17:00", ["Fri 10-09 17:00", "Fri 10-16 17:00", "Fri 10-23 17:00"]),
    ("ทุกสัปดาห์วันศุกร์ 5 โมงเย็น", ["Fri 10-09 17:00", "Fri 10-16 17:00", "Fri 10-23 17:00"]),
    ("every weekend at 11am", ["Sat 10-03 11:00", "Sun 10-04 11:00", "Sat 10-10 11:00"]),
    ("monthly on the 1st at 9am", ["Sun 11-01 09:00", "Tue 12-01 09:00", "Fri 01-01 09:00"]),
    ("on the 15th of every month at 18:00", ["Thu 10-15 18:00", "Sun 11-15 18:00", "Tue 12-15 18:00"]),
    ("ทุกวันที่ 1 ของเดือน 9 โมง", ["Sun 11-01 09:00", "Tue 12-01 09:00", "Fri 01-01 09:00"]),
    ("*/15 8-18 * * mon-fri", ["Mon 10-05 08:00", "Mon 10-05 08:15", "Mon 10-05 08:30"]),
    ("0 9 * * 1", ["Mon 10-05 09:00", "Mon 10-12 09:00", "Mon 10-19 09:00"]),
    ("30 6 1,15 * *", ["Thu 10-15 06:30", "Sun 11-01 06:30", "Sun 11-15 06:30"]),
])
def test_recurring_forms_mean_what_a_person_means(text, expected):
    assert at(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("in 20 minutes", "Sat 10-03 10:20"),
    ("อีก 20 นาที", "Sat 10-03 10:20"),
    ("in 2 hours", "Sat 10-03 12:00"),
    ("tomorrow at 9am", "Sun 10-04 09:00"),
    ("พรุ่งนี้ 9 โมง", "Sun 10-04 09:00"),
    ("today at 5pm", "Sat 10-03 17:00"),
    ("วันนี้ บ่าย 3 โมง", "Sat 10-03 15:00"),
    ("at 14:30", "Sat 10-03 14:30"),
    ("at 9am", "Sun 10-04 09:00"),                                   # already past today: tomorrow
    ("on 2026-10-05 at 09:00", "Mon 10-05 09:00"),
    ("พรุ่งนี้ 2 ทุ่ม", "Sun 10-04 20:00"),
    ("พรุ่งนี้ ตี 5", "Sun 10-04 05:00"),
    ("พรุ่งนี้ เที่ยง", "Sun 10-04 12:00"),
])
def test_one_off_forms(text, expected):
    s = ns.parse(text, now=NOW, tz=ZONE)
    assert s.kind == "once" and at(text, 2) == [expected]              # a one-off has exactly one run


def test_a_one_off_runs_once_and_then_never():
    s = ns.parse("in 20 minutes", now=NOW, tz=ZONE)
    first = ns.next_run(s, NOW)
    assert first == NOW + 1200 and ns.next_run(s, first) is None


def test_intervals_count_from_creation_and_never_drift_with_late_polling():
    s = ns.parse("every 30 minutes", now=NOW, tz=ZONE)
    assert ns.next_run(s, NOW + 1) == NOW + 1800
    assert ns.next_run(s, NOW + 1800) == NOW + 3600                       # strictly after
    assert ns.next_run(s, NOW + 1800 + 600) == NOW + 3600                 # polled late: still on the grid
    assert ns.next_run(s, NOW + 86400 * 5 + 5) == NOW + ((86400 * 5 + 5) // 1800 + 1) * 1800


def test_bare_interval_words_count_from_now_and_never_guess_a_time_of_day():
    for text, seconds in (("daily", 86400), ("ทุกวัน", 86400), ("weekly", 604800), ("hourly", 3600)):
        s = ns.parse(text, now=NOW, tz=ZONE)
        assert s.kind == "interval" and s.interval_s == seconds
    with pytest.raises(ns.ScheduleError, match="day and the time"):
        ns.parse("monthly", now=NOW, tz=ZONE)
    with pytest.raises(ns.ScheduleError, match="time of day"):
        ns.parse("every monday", now=NOW, tz=ZONE)


@pytest.mark.parametrize("text", ["", "   ", "sometime soon", "every blue moon", "every 10 seconds", "in 30 seconds", "every second", "tomorrow", "at ten",
                                  "* * * *", "monthly at 9am", "monthly on the 1st", "61 * * * *", "* 25 * * *", "*/0 * * * *", "5-1 * * * *", "on 2026-02-31 at 09:00", "x" * 300])
def test_what_is_not_understood_is_refused_not_guessed(text):
    with pytest.raises(ns.ScheduleError):
        ns.parse(text, now=NOW, tz=ZONE)


def test_the_refusal_lists_the_forms_that_are_understood():
    with pytest.raises(ns.ScheduleError) as info:
        ns.parse("whenever you feel like it", now=NOW, tz=ZONE)
    assert "every weekday at 8:30" in str(info.value) and "ทุกวัน 09:00" in str(info.value)


def test_a_time_already_past_today_is_refused_when_the_day_was_named():
    with pytest.raises(ns.ScheduleError, match="already in the past"):
        ns.parse("today at 8am", now=NOW, tz=ZONE)
    with pytest.raises(ns.ScheduleError, match="already in the past"):
        ns.parse("on 2026-10-02 at 09:00", now=NOW, tz=ZONE)


def test_day_of_month_and_day_of_week_both_restricted_means_either_like_classic_cron():
    s = ns.parse("0 12 13 * 5", now=NOW, tz=ZONE)                        # the 13th, or any Friday
    days = [datetime.fromtimestamp(t, TZ).strftime("%a %d") for t in ns.upcoming(s, NOW, 4)]
    assert days == ["Fri 09", "Tue 13", "Fri 16", "Fri 23"]


def test_a_cron_line_that_can_never_run_ends_instead_of_looping():
    s = ns.parse("0 0 31 2 *", now=NOW, tz=ZONE)                          # 31 February
    assert ns.next_run(s, NOW) is None


def test_sunday_is_zero_or_seven_and_names_work():
    a = at("0 8 * * 0")
    b = at("0 8 * * 7")
    c = at("0 8 * * sun")
    assert a == b == c == ["Sun 10-04 08:00", "Sun 10-11 08:00", "Sun 10-18 08:00"]


def test_describe_says_back_what_was_understood():
    assert ns.describe(ns.parse("every weekday at 8:30", now=NOW, tz=ZONE)) == "at 08:30 on Mon,Tue,Wed,Thu,Fri (Asia/Bangkok)"
    assert ns.describe(ns.parse("every 2 hours", now=NOW, tz=ZONE)) == "every 2 hours"
    assert "once, at 2026-10-04 09:00" in ns.describe(ns.parse("tomorrow at 9am", now=NOW, tz=ZONE))
    assert "on day 1 of the month" in ns.describe(ns.parse("monthly on the 1st at 9am", now=NOW, tz=ZONE))


def test_a_schedule_survives_being_stored_and_read_back():
    for text in ("every weekday at 8:30", "every 30 minutes", "in 20 minutes", "*/15 8-18 * * mon-fri", "monthly on the 1st at 9am"):
        s = ns.parse(text, now=NOW, tz=ZONE)
        back = ns.Schedule.from_dict(s.to_dict())
        assert ns.upcoming(back, NOW, 5) == ns.upcoming(s, NOW, 5)


def test_the_time_zone_is_part_of_the_schedule_and_a_wrong_name_is_refused():
    utc = ns.parse("every day at 9am", now=NOW, tz="UTC")
    bkk = ns.parse("every day at 9am", now=NOW, tz=ZONE)
    as_utc = datetime.fromtimestamp(ns.next_run(utc, NOW), ZoneInfo("UTC"))
    as_bkk = datetime.fromtimestamp(ns.next_run(bkk, NOW), TZ)
    assert (as_utc.hour, as_bkk.hour) == (9, 9)                           # the same words, 09:00 on each zone's own clock
    assert datetime.fromtimestamp(ns.next_run(bkk, NOW), ZoneInfo("UTC")).hour == 2
    with pytest.raises(ns.ScheduleError, match="unknown time zone"):
        ns.parse("every day at 9am", now=NOW, tz="Mars/Olympus")


def test_the_environment_zone_is_used_when_none_is_given(monkeypatch):
    monkeypatch.setenv("DELENTIA_TIMEZONE", "Asia/Bangkok")
    assert ns.parse("every day at 9am", now=NOW).tz == "Asia/Bangkok"
