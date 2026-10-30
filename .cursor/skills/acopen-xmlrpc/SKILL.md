---
name: acopen-xmlrpc
description: >-
  Read Acopen (Odoo) via XML-RPC using the project .env (ODOO_ACOPEN_*).
  Use when someone says accede a acopen, busca en acopen, or consulta acopen.
  Profile ACOPEN (Main, read-only). No create, write, or unlink.
---

# Acopen XML-RPC (Bruno)

Before naming a field or a model, open it under `/home/bruno-polypus/bruno_ project/odoo_17/addons` (`17.0+e.20260310`). Chilean localization (`l10n_cl`, `l10n_cl_edi`, `l10n_cl_edi_boletas`, `l10n_latam_invoice_document`) wins over a guess.

Read-only Acopen access. Credentials stay in the project `.env`. Never paste secrets.

When interpreting models or Chilean documents (DTE, RUT, taxes), also check l10n_cl
and Chilean localization modules (Odoo 17 Chilean localization).

## When to run

Invoke when someone mentions access, search, or query on Acopen
(«accede a acopen», «busca en acopen», «consulta acopen», «estado de la OC»).

Do **not** invent a browser login.

## Credentials

| Profile | Env prefix | Use |
|---|---|---|
| `ACOPEN` | `ODOO_ACOPEN_*` | Main, read-only |
| `ACOPEN_TEST` | `ODOO_ACOPEN_TEST_*` | Test (ask operator before writing) |

## Script

```text
scripts/acopen_xmlrpc_cli.py
```

```bash
PY="$HOME/repos/bruno_repo/.venv/bin/python"
CLI="$HOME/repos/bruno_repo/scripts/acopen_xmlrpc_cli.py"
```

### 1) Auth (first on a new Acopen task)

```bash
"$PY" "$CLI" auth --profile ACOPEN
```

### 2) Search

```bash
"$PY" "$CLI" search_read --profile ACOPEN \
  --model res.partner \
  --domain-json '[["name","ilike","Acopennova"]]' \
  --fields id,name,vat,email \
  --limit 10
```

ACOMIN (`company_id` 2):

```bash
"$PY" "$CLI" search_read --profile ACOPEN \
  --model stock.picking \
  --domain-json '[["company_id","=",2],["state","=","assigned"]]' \
  --context-json '{"allowed_company_ids":[2],"company_id":2}' \
  --fields id,name,partner_id,state,scheduled_date \
  --limit 10
```

### 3) Read by ids

```bash
"$PY" "$CLI" read --profile ACOPEN \
  --model stock.picking \
  --ids-json '[42]' \
  --fields id,name,partner_id,state
```

## Commands

Allowed: `version`, `auth`, `search_read`, `read`, `fields_get`.

Not available: `create`, `write`, `unlink`.

## Rules

1. Preflight `auth` before claiming Acopen is down.
2. Never print `ODOO_*_PASSWORD`.
3. Reply in Spanish with record facts (ids, names). Form URL: `{url}/web#id={id}&model={model}&view_type=form`
4. Companies: ACOMIN = 2, PENTAGON = 1, NOVATEX = 15. Say the name, never the number.
5. If credentials are missing from `.env`, say so and stop. Do not invent values.

## Related

PDF printouts: `.cursor/skills/acopen-download-report-pdf/SKILL.md`
GDE outgoing: `skills/odoo-gde/SKILL.md`
Incoming receipt: `skills/odoo-recepcion-po/SKILL.md`
