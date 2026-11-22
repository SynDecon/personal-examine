from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from datetime import date, time

_EXAM_HEADER = "考场座位号"
_GRID_TABLE_RE = re.compile(r'<table[^>]*\bid=["\']?grid[^"\'>]*["\']?[^>]*>(.*?)</table>', re.S)
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_TIME_RANGE_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[~～\-–—至]\s*(\d{1,2}):(\d{2})")
_SEMESTER_INPUT_RE = re.compile(r'name="semester\.id"[^>]*value="(\d+)"')
_SEMESTER_TEXT_RE = re.compile(r"semester\.id=(\d+)")
_SEMESTER_JS_RE = re.compile(r'getSemesters\([^)]*?value\s*:\s*"(\d+)"')
_SEMESTER_CALENDAR_RE = re.compile(r'semesterCalendar\(\{[^}]*?value\s*:\s*"(\d+)"')
_EXAM_BATCH_RE = re.compile(r"examBatch\.id=(\d+)")


@dataclass
class Exam:
    code: str
    name: str
    category: str
    day: date
    start: time
    end: time
    room: str
    seat: str
    status: str
    note: str


def _text(cell: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", cell))).strip()


def _normalize_room(room: str) -> str:
    room = room.replace("鹤壁工程技术学院", " ")
    room = re.sub(r"\s+", " ", room).strip()
    room = re.sub(r"\(\s+", "(", room)
    return re.sub(r"\s+\)", ")", room)


def parse_semester_id(html: str) -> str | None:
    for pattern in (
        _SEMESTER_INPUT_RE,
        _SEMESTER_TEXT_RE,
        _SEMESTER_JS_RE,
        _SEMESTER_CALENDAR_RE,
    ):
        found = pattern.search(html)
        if found:
            return found.group(1)
    return None


def parse_exam_batch_id(html: str) -> str | None:
    found = _EXAM_BATCH_RE.search(html)
    return found.group(1) if found else None


def _parse_row(row: str) -> Exam | None:
    cells = [_text(cell) for cell in _CELL_RE.findall(row)]
    if len(cells) < 7:
        return None
    code, name, category, day_text, span, room, seat = cells[:7]
    status = cells[7] if len(cells) > 7 else ""
    note = cells[8] if len(cells) > 8 else ""

    date_match = _DATE_RE.search(day_text)
    span_match = _TIME_RANGE_RE.search(span)
    if not date_match or not span_match:
        raise ValueError(f"考试行缺少日期或时间: {name or code}")
    year, month, day_number = (int(part) for part in date_match.groups())
    start_hour, start_minute, end_hour, end_minute = (int(part) for part in span_match.groups())

    return Exam(
        code=code,
        name=name,
        category=category,
        day=date(year, month, day_number),
        start=time(start_hour, start_minute),
        end=time(end_hour, end_minute),
        room=_normalize_room(room),
        seat=seat,
        status=status,
        note=note,
    )


def parse_exam_table(html: str) -> list[Exam]:
    if _EXAM_HEADER not in html:
        raise ValueError("页面中没有「考场座位号」列，可能不是考试页面或登录已失效")

    exams: list[Exam] = []
    seen: set[tuple] = set()
    grid = _GRID_TABLE_RE.search(html)
    scope = grid.group(1) if grid else html
    for row in _ROW_RE.findall(scope):
        exam = _parse_row(row)
        if exam is None:
            continue
        key = (exam.code, exam.name, exam.day, exam.start, exam.end, exam.room, exam.seat)
        if key in seen:
            continue
        seen.add(key)
        exams.append(exam)

    exams.sort(key=lambda item: (item.day, item.start, item.name))
    return exams