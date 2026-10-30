---
name: chat-log
description: >
  Read this speaker's Telegram messages and the Cloud Agent replies that were
  sent back. Use when they ask what was said, what you answered, to repeat a
  reply, or what went out on Telegram today. Do not use it for mail, Acopen,
  or memory of past commercial tasks.
---

# Chat log (this speaker)

Use only when they ask about the conversation itself: what they wrote, what you answered, or to repeat a reply. One script, then stop.

```bash
python3 scripts/chat_log.py --user-id <telegram_user_id> [--direction both|inbound|outbound] [--date YYYY-MM-DD] [--around HH:MM] [--window N] [--q "words"]
```

Clock: America/Santiago. Default day is today. Speaker id comes from the prompt. Never say the id.

| `--direction` | What it is |
|---|---|
| `inbound` | Text they sent on Telegram |
| `outbound` | Cloud Agent answer the bridge sent back on Telegram |
| `both` | Both, in time order (default) |

## Extract time from the user message

If the user names a time ("a las 21:30", "cerca de las 9", "por la tarde"), extract it as HH:MM (24 h, Chile clock) and pass it with `--around`. Default `--window` is 30 (±30 min). Widen to 60 if they said "por la tarde" or another vague expression.

Examples:

- "lo que me respondiste a las 9 de la mañana" → `--around 09:00`
- "el mensaje de cerca de las 21:30" → `--around 21:30`
- "lo de la tarde" → `--around 15:00 --window 120`
- No time mentioned → omit `--around` (full day)

Only this speaker's rows are returned. Do not drop `--user-id`.

## How to answer

- Commercial Spanish. No paths, ids, skills, or how the log works.
- `inbound` is what they wrote. `outbound` is what you answered.
- `sender_name` is who sent it on Telegram. `msg_date` is the Telegram time. Say the name and that time. Never print the user id.
- If `count` is 0: say there is no record for that day. Do not invent a reply.
- If `truncated` is true: say the list is the latest part of the day, not every line.
- If `has_doc` is true and they want that file, the final message must contain the exact `TELEGRAM_DOCUMENT:` line using `doc_path`. Do not describe the path.
- Do not open `data/messages.jsonl` by hand. Do not read another person's rows.

A recall of a past order, tender, or task is `memory-recall`, not this skill.
