from __future__ import annotations

import sys
from datetime import date, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from icalendar import Calendar

from src.ics_builder import build_calendar
from src.parser import Exam

SETTINGS = {"timezone": "Asia/Shanghai", "calendar_name": "考试日程"}


def _exam(seat: str = "12", day: date = date(2027, 1, 13)) -> Exam:
    return Exam(
        code="X001.001",
        name="示例课程一",
        category="期末考试",
        day=day,
        start=time(8, 0),
        end=time(9, 40),
        room="A310(1号教学楼)",
        seat=seat,
        status="正常",
        note="",
    )


def _events(exams):
    calendar = Calendar.from_ical(build_calendar(exams, SETTINGS).to_ical())
    return calendar.walk("VEVENT")


def test_event_fields():
    events = _events([_exam()])
    assert len(events) == 1
    event = events[0]
    assert event["summary"] == "示例课程一"
    assert event["location"] == "A310(1号教学楼)"
    assert "考场座位号：12" in event["description"]


def test_timezone_offset():
    event = _events([_exam()])[0]
    start = event.decoded("dtstart")
    assert start.utcoffset() == timedelta(hours=8)


def test_uid_stable_when_seat_changes():
    first = str(_events([_exam(seat="12")])[0]["uid"])
    second = str(_events([_exam(seat="33")])[0]["uid"])
    assert first == second


def test_uid_differs_by_date():
    first = str(_events([_exam(day=date(2027, 1, 13))])[0]["uid"])
    second = str(_events([_exam(day=date(2027, 1, 14))])[0]["uid"])
    assert first != second


def test_missing_seat_placeholder():
    event = _events([_exam(seat="")])[0]
    assert "考场座位号：待公布" in event["description"]