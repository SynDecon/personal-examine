from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from hashlib import sha1
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event, Timezone, TimezoneStandard

from .parser import Exam


def _timezone_component(tzid: str, tz: ZoneInfo) -> Timezone:
    offset = datetime(2026, 1, 1, tzinfo=tz).utcoffset() or timedelta(0)
    component = Timezone()
    component.add("tzid", tzid)
    standard = TimezoneStandard()
    standard.add("dtstart", datetime(1970, 1, 1))
    standard.add("tzoffsetfrom", offset)
    standard.add("tzoffsetto", offset)
    standard.add("tzname", "CST")
    component.add_component(standard)
    return component


def _uid(exam: Exam) -> str:
    raw = f"{exam.code}|{exam.day.isoformat()}|{exam.start.strftime('%H:%M')}"
    return sha1(raw.encode("utf-8")).hexdigest()[:24] + "@hebi-exam"


def _description(exam: Exam) -> str:
    lines = [
        f"考场座位号：{exam.seat or '待公布'}",
        f"考试类别：{exam.category}",
    ]
    if exam.status and exam.status != "正常":
        lines.append(f"考试情况：{exam.status}")
    if exam.note:
        lines.append(f"说明：{exam.note}")
    return "\n".join(lines)


def build_calendar(exams: list[Exam], settings: dict) -> Calendar:
    tzid = str(settings.get("timezone") or "Asia/Shanghai")
    calendar_name = str(settings.get("calendar_name") or "考试日程")
    tz = ZoneInfo(tzid)
    now = datetime.now(dt_timezone.utc)

    calendar = Calendar()
    calendar.add("prodid", "-//hebi-exam//CN")
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("x-wr-calname", calendar_name)
    calendar.add("x-wr-timezone", tzid)
    calendar.add_component(_timezone_component(tzid, tz))

    for exam in exams:
        event = Event()
        event.add("summary", exam.name)
        event.add("dtstart", datetime.combine(exam.day, exam.start, tzinfo=tz))
        event.add("dtend", datetime.combine(exam.day, exam.end, tzinfo=tz))
        event.add("location", exam.room)
        event.add("description", _description(exam))
        event.add("uid", _uid(exam))
        event.add("dtstamp", now)
        event.add("last-modified", now)
        event.add("sequence", 0)
        calendar.add_component(event)

    return calendar