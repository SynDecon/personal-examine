from __future__ import annotations

import sys
from datetime import date, time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parser import parse_exam_table, parse_semester_id

FIXTURE = """
<html><body>
<form><input type="hidden" name="semester.id" value="322"></form>
<table class="gridtable">
<thead class="gridhead"><tr>
<th>课程序号</th><th>课程名称</th><th>考试类别</th><th>考试日期</th>
<th>考试安排</th><th>考试地点</th><th>考场座位号</th><th>考试情况</th><th>其它说明</th>
</tr></thead>
<tbody id="grid1_data">
<tr class="griddata-even       "><td>X001.001</td><td>示例课程一</td><td>期末考试</td><td>2027-01-13</td>
<td>08:00~09:40</td>
<td><a href="http://example/eams/stdExamTable!downloadExamroomSeat.action?examRoom.id=1" target="_blank">A310(鹤壁工程技术学院 1号教学楼)</a></td>
<td>12</td>
<td>正常</td><td></td></tr>
<tr class="griddata-odd     "><td>X002.001</td><td>示例课程二</td><td>期末考试</td><td>2027-01-11</td>
<td>14:30-16:10</td>
<td><a href="http://example/eams/stdExamTable!downloadExamroomSeat.action?examRoom.id=2" target="_blank">A211(鹤壁工程技术学院 1号教学楼)</a></td>
<td></td>
<td>正常</td><td></td></tr>
</tbody></table>
</body></html>
"""

EMPTY_FIXTURE = """
<table><thead><tr><th>考场座位号</th></tr></thead><tbody id="grid2_data"></tbody></table>
"""


def test_parse_fields():
    exams = parse_exam_table(FIXTURE)
    assert len(exams) == 2
    first = exams[0]
    assert first.code == "X002.001"
    assert first.name == "示例课程二"
    assert first.category == "期末考试"
    assert first.day == date(2027, 1, 11)
    assert first.start == time(14, 30)
    assert first.end == time(16, 10)
    assert first.seat == ""


def test_sort_by_date_and_time():
    exams = parse_exam_table(FIXTURE)
    assert [exam.day for exam in exams] == [date(2027, 1, 11), date(2027, 1, 13)]


def test_room_normalized():
    exams = parse_exam_table(FIXTURE)
    assert exams[1].room == "A310(1号教学楼)"


def test_seat_parsed():
    exams = parse_exam_table(FIXTURE)
    assert exams[1].seat == "12"


def test_empty_table_is_valid():
    assert parse_exam_table(EMPTY_FIXTURE) == []


def test_missing_header_raises():
    with pytest.raises(ValueError):
        parse_exam_table("<html><body>统一身份认证</body></html>")


def test_bad_time_raises():
    broken = FIXTURE.replace("08:00~09:40", "待定")
    with pytest.raises(ValueError):
        parse_exam_table(broken)


def test_parse_semester_id():
    assert parse_semester_id(FIXTURE) == "322"


def test_parse_semester_id_from_js():
    html = '<script>getSemesters(el,{empty:"false",value:"322"},"");</script>'
    assert parse_semester_id(html) == "322"