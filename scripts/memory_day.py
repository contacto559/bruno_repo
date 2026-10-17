#!/usr/bin/env python3
"""List one speaker-day diary grouped by hour. No match cap. No secrets.

If the day has more than DOC_THRESHOLD tasks, also write a readable copy under
media/outbound/ so Telegram can attach the full day (TELEGRAM_DOCUMENT).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MEMORIES = ROOT / "memories"
OUTBOUND = ROOT / "media" / "outbound"
TZ = ZoneInfo("America/Santiago")
SPEAKER_RE = re.compile(r"^\d{3,20}$")
LINE_RE = re.compile(r"^(\d{2}):(\d{2})\s*\|")
DOC_THRESHOLD = 25


def chile_today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def task_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line[:500])
    return lines


def group_by_hour(lines: list[str]) -> list[dict]:
    buckets: dict[str, list[str]] = {}
    order: list[str] = []
    for line in lines:
        match = LINE_RE.match(line)
        hour = match.group(1) if match else "??"
        if hour not in buckets:
            buckets[hour] = []
            order.append(hour)
        buckets[hour].append(line)
    return [{"hour": hour, "tasks": buckets[hour]} for hour in order]


def write_outbound(day: str, speaker: str, hours: list[dict]) -> Path:
    OUTBOUND.mkdir(parents=True, exist_ok=True)
    dest = OUTBOUND / f"memory-{day}-{speaker}.md"
    parts = [f"# Memory {day}", "", "Tasks by hour. No secrets.", ""]
    for block in hours:
        parts.append(f"## {block['hour']}:00")
        parts.append("")
        for task in block["tasks"]:
            parts.append(f"- {task}")
        parts.append("")
    dest.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="One speaker-day grouped by hour.")
    parser.add_argument("--speaker-id", required=True)
    parser.add_argument("--date", default="", help="YYYY-MM-DD Chile (default: today).")
    args = parser.parse_args()

    speaker = args.speaker_id.strip()
    if not SPEAKER_RE.match(speaker):
        print(json.dumps({"ok": False, "error": "bad_speaker_id", "count": 0, "hours": []}))
        return 2

    day = (args.date or "").strip() or chile_today()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        print(json.dumps({"ok": False, "error": "bad_date", "count": 0, "hours": []}))
        return 2

    path = MEMORIES / f"{day}-{speaker}.md"
    if not path.is_file():
        print(
            json.dumps(
                {
                    "ok": True,
                    "count": 0,
                    "hours": [],
                    "file": path.name,
                    "date": day,
                    "attach": False,
                },
                ensure_ascii=False,
            )
        )
        return 0

    lines = task_lines(path)
    hours = group_by_hour(lines)
    payload: dict = {
        "ok": True,
        "count": len(lines),
        "hours": hours,
        "file": path.name,
        "date": day,
        "attach": False,
    }
    if len(lines) > DOC_THRESHOLD:
        dest = write_outbound(day, speaker, hours)
        payload["attach"] = True
        payload["outbound"] = str(dest.resolve())
        payload["telegram_document"] = (
            f"TELEGRAM_DOCUMENT: {dest.resolve()} | Memory {day}"
        )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
