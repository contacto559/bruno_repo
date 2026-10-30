#!/usr/bin/env python3
"""Read the Telegram bridge message log. No secrets. No network.

File: data/messages.jsonl (one JSON object per line).
direction=inbound  -> what the person sent on Telegram.
direction=outbound -> the Cloud Agent answer the bridge sent back on Telegram.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "data" / "messages.jsonl"
TZ = ZoneInfo("America/Santiago")
DEFAULT_LIMIT = 30
MAX_LIMIT = 80


def chile_today() -> date:
    return datetime.now(TZ).date()


def parse_day(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_hhmm(raw: str):
    """Parse HH:MM into a time, or None."""
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    return None


def parse_ts(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=TZ)
    return stamp.astimezone(TZ)


def tokens(query: str) -> list[str]:
    parts = [part.lower() for part in query.split() if part.strip()]
    return [part for part in parts if len(part) >= 2][:12]


def load_rows() -> list[dict]:
    if not LOG_PATH.is_file():
        return []
    rows: list[dict] = []
    with LOG_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip().lstrip("\ufeff")
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def emit(payload: dict, code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description="Read the chat log.")
    parser.add_argument("--user-id", required=True, help="Telegram user id of the speaker.")
    parser.add_argument(
        "--direction",
        choices=("both", "inbound", "outbound"),
        default="both",
        help="inbound=Telegram text they sent; outbound=Cloud Agent reply sent back.",
    )
    parser.add_argument("--date", default="", help="Chile day YYYY-MM-DD. Default: today.")
    parser.add_argument(
        "--around",
        default="",
        help="Central time HH:MM (Chile). Keep messages within --window minutes on each side.",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=30,
        help="Minutes on each side of --around (default 30, max 120).",
    )
    parser.add_argument("--q", default="", help="Optional words that must all appear in the text.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()

    raw_user = str(args.user_id).strip()
    if not raw_user.lstrip("-").isdigit():
        return emit({"ok": False, "error": "bad_user_id", "count": 0, "messages": []}, 2)
    user_id = int(raw_user)

    day = parse_day(args.date) if args.date.strip() else chile_today()
    if day is None:
        return emit({"ok": False, "error": "bad_date", "count": 0, "messages": []}, 2)

    target_time = parse_hhmm(args.around) if args.around.strip() else None
    if args.around.strip() and target_time is None:
        return emit({"ok": False, "error": "bad_around", "count": 0, "messages": []}, 2)
    window_mins = args.window
    if window_mins < 1:
        window_mins = 1
    if window_mins > 120:
        window_mins = 120
    half = timedelta(minutes=window_mins)

    limit = args.limit
    if limit < 1:
        limit = 1
    if limit > MAX_LIMIT:
        limit = MAX_LIMIT

    want = tokens(args.q)
    matched: list[dict] = []
    for row in load_rows():
        if row.get("user_id") != user_id:
            continue
        direction = str(row.get("direction") or "")
        if direction not in {"inbound", "outbound"}:
            continue
        if args.direction != "both" and direction != args.direction:
            continue
        stamp = parse_ts(str(row.get("ts") or ""))
        if stamp is None or stamp.date() != day:
            continue
        if target_time is not None:
            center = datetime.combine(stamp.date(), target_time, tzinfo=TZ)
            if not (center - half <= stamp <= center + half):
                continue
        text = str(row.get("text") or "")
        if want and not all(word in text.lower() for word in want):
            continue
        doc = row.get("doc_path")
        doc_path = str(doc).strip() if isinstance(doc, str) and doc.strip() else None
        matched.append(
            {
                "ts": stamp.isoformat(),
                "msg_date": row.get("msg_date"),
                "direction": direction,
                "sender_name": row.get("sender_name"),
                "sender_username": row.get("sender_username"),
                "text": text,
                "has_doc": bool(doc_path),
                "doc_path": doc_path,
            }
        )

    matched.sort(key=lambda item: item["ts"])
    clipped = matched[-limit:]
    return emit(
        {
            "ok": True,
            "date": day.isoformat(),
            "around": target_time.strftime("%H:%M") if target_time else None,
            "window_mins": window_mins if target_time else None,
            "window_applied": target_time is not None,
            "direction": args.direction,
            "count": len(clipped),
            "truncated": len(matched) > len(clipped),
            "messages": clipped,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
