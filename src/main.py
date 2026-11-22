from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

import yaml

from .fetcher import FetchError, LoginError, create_session, fetch_exam_table
from .ics_builder import build_calendar
from .parser import parse_exam_table

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
OUTPUT_FILE = ROOT / "output" / "考试.ics"


def _load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _set_output(**values: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={str(value).replace(chr(10), ' ')}\n")


def _read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def run(html_path: str | None) -> int:
    if html_path:
        html = Path(html_path).read_text(encoding="utf-8", errors="replace")
    else:
        user = os.environ.get("SCHOOL_USER", "")
        password = os.environ.get("SCHOOL_PASS", "")
        if not user or not password:
            raise LoginError("缺少 SCHOOL_USER / SCHOOL_PASS")
        html = fetch_exam_table(create_session(user, password))

    exams = parse_exam_table(html)
    if not exams:
        raise FetchError("考试页面解析到 0 场考试，未写入文件（避免清空已有日历）")

    settings = _read_yaml(CONFIG_DIR / "settings.yaml")
    calendar = build_calendar(exams, settings)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = OUTPUT_FILE.with_name(OUTPUT_FILE.name + ".tmp")
    temp_file.write_bytes(calendar.to_ical())
    temp_file.replace(OUTPUT_FILE)
    return len(exams)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", help="本地考试页面 HTML 路径，跳过抓取")
    args = parser.parse_args()
    _load_dotenv()
    try:
        count = run(args.html)
        print(f"已生成 {OUTPUT_FILE}，共 {count} 场考试")
        _set_output(valid="true", error="", exams=str(count))
    except Exception as exc:
        _set_output(valid="false", error=str(exc))
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()