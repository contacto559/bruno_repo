#!/usr/bin/env python3
"""Fast keyword search in speaker-day memory files. No LLM. No secrets.

Reads memories/YYYY-MM-DD-<speaker_id>.md only. Skips MEMORY.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MEMORIES = ROOT / "memories"
TZ = ZoneInfo("America/Santiago")
SPEAKER_RE = re.compile(r"^\d{3,20}$")
FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d+)\.md$")
DEFAULT_DAYS = 90
MAX_DAYS = 365
# Keyword search only. Day dumps use memory_day.py and are not capped here.
MAX_KEYWORD_MATCHES = 100


def parse_day(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def chile_today() -> date:
    return datetime.now(TZ).date()


def tokens(query: str) -> list[str]:
    parts = [p.lower() for p in re.split(r"\s+", query.strip()) if p.strip()]
    return [p for p in parts if len(p) >= 2][:12]


def line_matches(text: str, words: list[str]) -> bool:
    hay = text.lower()
    return all(word in hay for word in words)


def main() -> int:
    parser = argparse.ArgumentParser(description="Search speaker memory files.")
    parser.add_argument("--speaker-id", required=True)
    parser.add_argument(
        "--q",
        default="",
        help="Keywords / OC / WR / GDE / import / customer. Empty = list lines in the date range.",
    )
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Look back N Chile days.")
    parser.add_argument("--desde", default="", help="Inclusive YYYY-MM-DD.")
    parser.add_argument("--hasta", default="", help="Inclusive YYYY-MM-DD.")
    args = parser.parse_args()

    speaker = args.speaker_id.strip()
    if not SPEAKER_RE.match(speaker):
        print(json.dumps({"ok": False, "error": "bad_speaker_id", "matches": [], "count": 0}))
        return 2

    words = tokens(args.q)
    list_range = not words and bool(args.desde.strip() and args.hasta.strip())
    if not words and not list_range:
        print(json.dumps({"ok": False, "error": "empty_query", "matches": [], "count": 0}))
        return 2

    today = chile_today()
    start = parse_day(args.desde)
    end = parse_day(args.hasta)
    if args.desde and start is None:
        print(json.dumps({"ok": False, "error": "bad_desde", "matches": [], "count": 0}))
        return 2
    if args.hasta and end is None:
        print(json.dumps({"ok": False, "error": "bad_hasta", "matches": [], "count": 0}))
        return 2
    if start is None and end is None:
        days = max(1, min(int(args.days or DEFAULT_DAYS), MAX_DAYS))
        start = today - timedelta(days=days)
        end = today
    elif start is None:
        start = end - timedelta(days=MAX_DAYS) if end else today - timedelta(days=DEFAULT_DAYS)
    elif end is None:
        end = today
    if start > end:
        start, end = end, start

    matches: list[dict] = []
    scanned = 0
    if MEMORIES.is_dir():
        for path in sorted(MEMORIES.glob(f"*-{speaker}.md"), reverse=True):
            parsed = FILE_RE.match(path.name)
            if not parsed:
                continue
            day = parse_day(parsed.group(1))
            if day is None or day < start or day > end:
                continue
            scanned += 1
            for index, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if list_range or line_matches(line, words):
                    matches.append({"file": path.name, "line": index, "text": line[:400]})
                    if not list_range and len(matches) >= MAX_KEYWORD_MATCHES:
                        break
            if not list_range and len(matches) >= MAX_KEYWORD_MATCHES:
                break

    print(
        json.dumps(
            {
                "ok": True,
                "count": len(matches),
                "matches": matches,
                "scanned_files": scanned,
                "desde": start.isoformat(),
                "hasta": end.isoformat(),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
