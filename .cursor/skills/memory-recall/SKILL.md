---
name: memory-recall
description: >
  Recall past work for this Telegram speaker. Use when they ask what we did,
  the last time, remember when, which tender, order X, event Y, a theme, hace
  N días, or any past reference. Search memory; if nothing matches, ask when
  it was or leave the doubt. Never invent.
---

# Memory recall (this speaker)

Use when they ask about the past or cite something past (order, tender, event, theme, "hace N días").
Do **not** open `memories/MEMORY.md` or the whole `memories/` folder.
Do **not** invent a day or an order that is not on disk.
Do **not** write a "correction" that denies lines already on disk unless you re-read that full day first (`memory_day.py`).

Speaker id = Telegram user id from the prompt (digits only). Never say the id.

```text
scripts/memory_day.py
scripts/memory_topics.py
scripts/memory_search.py
scripts/memory_write.py
```

Clock: America/Santiago.

## 1) One day («¿qué hicimos ayer / el miércoles?»)

- No date → one question: «¿De qué día?»
- With a date:

```bash
python3 scripts/memory_day.py --speaker-id <telegram_user_id> --date YYYY-MM-DD
```

Answer in commercial Spanish **by hour** (`hours[].hour` + tasks). Include every hour returned. Do not drop the evening because the morning was long.

If `count = 0`: say there is no record for that day. Do not invent.

If `attach` is true (`count` > 25): short hour index in chat, then the exact `telegram_document` line from the JSON so the full day is attached. Do not cut tasks.

## 2) Theme (agendamiento, Comex, Ariba, customer, …)

```bash
python3 scripts/memory_topics.py --q "<keywords>" --speaker-id <telegram_user_id>
```

- If `topics` is not empty: answer from `title` + `summary`. Use `refs` only to open the file and verify; never print paths.
- If `topics` is empty and `fallback` has lines: those are hints only (max 30). Do not treat them as the whole day.
- If both empty: ask when it was or leave the doubt. Never invent.

## 3) Concrete keyword (order / event id)

```bash
python3 scripts/memory_search.py --speaker-id <telegram_user_id> --q "<keywords>" [--days N]
```

Keyword search is capped. A full day is never this command — use `memory_day.py`.

If `count = 0`: do **not** invent.

## Stop

- Never invent a summary for a day that is not on disk.
- Never print Telegram ids, paths, or secrets.
- Never deny a topic that `memory_day.py` already lists for that date.
- After a real work task (not a recall-only question), also run `memory_write.py`
  with refs (OC, Ariba event, customer, theme) so later search can find it.
