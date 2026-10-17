---
name: acopen-download-report-pdf
description: >-
  Download an Odoo 17 QWeb PDF (sale.order, account.move, stock.picking) via
  ir.actions.report + HTTP session, using the project .env. Use when someone
  asks to imprimir PDF, enviar PDF, PDF del albaran, or PDF de la orden.
  Profile ACOPEN (read-only). The bridge sends the file when the final message
  includes TELEGRAM_DOCUMENT.
---

# Acopen — download QWeb PDF (Bruno)

Read-only PDF download. Credentials from the project `.env`. Profile `ACOPEN`.

## When

- «imprimir PDF», «enviar PDF», «PDF del albarán», «PDF de la guía», «PDF de la OC»
- Any request to get an Odoo printout as a file

Do **not** use the browser on Acopen. Do **not** call `/xmlrpc/2/report`.

## Pipeline

1. Resolve record (`--res-id` or `--name-value` e.g. `WH/OUT/00042`).
2. Resolve `ir.actions.report` (`qweb-pdf`; sale orders prefer `sale.report_saleorder_raw`).
3. `POST /web/session/authenticate` → CSRF from `/web?db=` → `GET /report/pdf/…`
   (fallback `POST /report/download`).
4. Assert `%PDF-` → copy to `media/outbound/`.
5. The final assistant message **must** include `telegram_line` so the bridge attaches the file.

## Command

```bash
PY="$HOME/repos/bruno_repo/.venv/bin/python"
CLI="$HOME/repos/bruno_repo/scripts/acopen_download_report_pdf.py"

"$PY" "$CLI" download --profile ACOPEN --model stock.picking --name-value WH/OUT/00042
```

Other models: `--model account.move` or `--model sale.order`.
Force report: `--report-name stock.report_deliveryslip`.

## Delivery

JSON includes `telegram_line`, for example:

```text
TELEGRAM_DOCUMENT: /home/bruno-polypus/repos/bruno_repo/media/outbound/WH_OUT_00042_55.pdf | Albarán WH/OUT/00042
```

Put that line in the **final** assistant message (plus a short Spanish note).
The bridge strips the marker and sends the PDF.

Do not say the PDF was sent without `TELEGRAM_DOCUMENT:`.

## Anti-patterns

| Forbidden | Use instead |
|---|---|
| Browser on Acopen | This script |
| `/xmlrpc/2/report` | HTTP `/report/pdf` |
| Invented `report_name` | `ir.actions.report` resolution |
| Save HTML as `.pdf` | Script asserts `%PDF-` |
| `create` / `write` / `unlink` | This skill only downloads |

## Related

Search/RPC: `.cursor/skills/acopen-xmlrpc/SKILL.md`
