#!/usr/bin/env python3
"""Search topic cards under memories/topics/. Compact: title, summary, refs.

Optional diary fallback (--speaker-id) when no card matches: at most 30 keyword hits.
Never prints secrets. Never dumps a full day.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TOPICS = ROOT / "memories" / "topics"
MEMORIES = ROOT / "memories"
TZ = ZoneInfo("America/Santiago")
SPEAKER_RE = re.compile(r"^\d{3,20}$")
FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d+)\.md$")
FALLBACK_CAP = 30
DEFAULT_DAYS = 90


def tokens(query: str) -> list[str]:
    parts = [p.lower() for p in re.split(r"\s+", query.strip()) if p.strip()]
    return [p for p in parts if len(p) >= 2][:12]


def parse_card(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace")
    title = path.stem
    tags: list[str] = []
    summary_lines: list[str] = []
    refs: list[str] = []
    section = ""
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip() or title
            section = ""
            continue
        low = stripped.lower()
        if low.startswith("tags:"):
            tags = [t.strip() for t in stripped.split(":", 1)[1].split(",") if t.strip()]
            section = ""
            continue
        if low.startswith("summary:"):
            rest = stripped.split(":", 1)[1].strip()
            section = "summary"
            if rest:
                summary_lines.append(rest)
            continue
        if low == "refs:" or low.startswith("refs:"):
            section = "refs"
            rest = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
            if rest.startswith("- "):
                refs.append(rest[2:].strip())
            elif rest:
                refs.append(rest)
            continue
        if section == "summary" and stripped and not stripped.startswith("- "):
            summary_lines.append(stripped)
            continue
        if section == "refs" and stripped.startswith("- "):
            refs.append(stripped[2:].strip())
    return {
        "title": title,
        "tags": tags,
        "summary": " ".join(summary_lines).strip(),
        "refs": refs,
        "file": path.name,
    }


def card_matches(card: dict, words: list[str]) -> bool:
    hay = " ".join(
        [card["title"], card["summary"], " ".join(card["tags"]), " ".join(card["refs"])]
    ).lower()
    return all(word in hay for word in words)


def diary_fallback(speaker: str, words: list[str]) -> list[dict]:
    if not words or not MEMORIES.is_dir() or not SPEAKER_RE.match(speaker):
        return []
    today = datetime.now(TZ).date()
    start = today - timedelta(days=DEFAULT_DAYS)
    hits: list[dict] = []
    for path in sorted(MEMORIES.glob(f"*-{speaker}.md"), reverse=True):
        parsed = FILE_RE.match(path.name)
        if not parsed:
            continue
        try:
            day = datetime.strptime(parsed.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if day < start or day > today:
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            hay = line.lower()
            if all(word in hay for word in words):
                hits.append({"file": path.name, "text": line[:240]})
                if len(hits) >= FALLBACK_CAP:
                    return hits
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Search memory topic cards.")
    parser.add_argument("--q", required=True, help="Theme keywords.")
    parser.add_argument(
        "--speaker-id",
        default="",
        help="Optional. Diary fallback only when no card matches.",
    )
    args = parser.parse_args()

    words = tokens(args.q)
    if not words:
        print(json.dumps({"ok": False, "error": "empty_query", "topics": [], "count": 0}))
        return 2

    cards: list[dict] = []
    if TOPICS.is_dir():
        for path in sorted(TOPICS.glob("*.md")):
            if path.name.upper() == "README.MD":
                continue
            card = parse_card(path)
            if card_matches(card, words):
                cards.append(card)

    payload: dict = {
        "ok": True,
        "count": len(cards),
        "topics": cards,
        "fallback": [],
    }
    speaker = (args.speaker_id or "").strip()
    if not cards and speaker:
        if not SPEAKER_RE.match(speaker):
            print(json.dumps({"ok": False, "error": "bad_speaker_id", "topics": [], "count": 0}))
            return 2
        payload["fallback"] = diary_fallback(speaker, words)
        payload["fallback_count"] = len(payload["fallback"])
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
