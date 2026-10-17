#!/usr/bin/env python3
"""Append one operational memory line for a Telegram speaker (Chile date).

Writes memories/YYYY-MM-DD-<speaker_id>.md. Never prints secrets.
Does not read .env. Does not touch MEMORY.md.
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
TZ = ZoneInfo("America/Santiago")
SPEAKER_RE = re.compile(r"^\d{3,20}$")


def chile_today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def chile_hm() -> str:
    return datetime.now(TZ).strftime("%H:%M")


def one_line(raw: str) -> str:
    text = " ".join(raw.replace("\r", " ").replace("\n", " ").split())
    if not text:
        raise SystemExit(json.dumps({"ok": False, "error": "empty_entry"}))
    return text[:500]


def main() -> int:
    parser = argparse.ArgumentParser(description="Append one speaker-day memory line.")
    parser.add_argument("--speaker-id", required=True, help="Telegram user id (digits).")
    parser.add_argument(
        "--entry",
        required=True,
        help="One operational line (refs: OC, WR, GDE, import, package, customer).",
    )
    parser.add_argument("--date", default="", help="YYYY-MM-DD Chile (default: today).")
    args = parser.parse_args()

    speaker = args.speaker_id.strip()
    if not SPEAKER_RE.match(speaker):
        print(json.dumps({"ok": False, "error": "bad_speaker_id"}))
        return 2

    day = (args.date or "").strip() or chile_today()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        print(json.dumps({"ok": False, "error": "bad_date"}))
        return 2

    entry = one_line(args.entry)
    if not re.match(r"^\d{2}:\d{2}\s*\|", entry):
        entry = f"{chile_hm()} | {entry}"

    MEMORIES.mkdir(parents=True, exist_ok=True)
    path = MEMORIES / f"{day}-{speaker}.md"
    if not path.exists():
        path.write_text(
            f"# Memory {day} speaker {speaker}\n\n"
            "One line per task. No secrets. Chile time.\n\n",
            encoding="utf-8",
        )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{entry}\n")

    print(json.dumps({"ok": True, "file": path.name, "entry": entry}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
