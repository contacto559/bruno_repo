---
name: acopen-prod-test
description: Switching and correct use of Acopen production vs test. Use when the user asks to change environment, when connecting to Acopen, or when a script must run against the chosen environment.
metadata:
  openclaw:
    requires:
      bins: ["python3"]
      env:
        - "ODOO_URL"
        - "ODOO_DB"
        - "ODOO_USER"
        - "ODOO_PASSWORD"
        - "ODOO_ACOPEN_TEST_URL"
        - "ODOO_ACOPEN_TEST_DB"
        - "ODOO_ACOPEN_TEST_USER"
        - "ODOO_ACOPEN_TEST_PASSWORD"
        - "ODOO_ACOPEN_USE_TEST"
---

# Acopen production ↔ test

Odoo behavior, including Chilean localization, is the tree at `/home/bruno-polypus/bruno_ project/odoo_17/addons` (`17.0+e.20260310`). Read the module before a write. If this skill and that code disagree, the code wins.

Julio only accesses Acopen. This skill defines how to switch between production and test.

The credential source for deployed runtime use is **`/root/.openclaw_julio/.env`** (Julio state, same pattern as Sofia’s state `.env`); this skill only consumes the environment variables loaded from there.

## Production

- Use `ODOO_URL`, `ODOO_DB`, `ODOO_USER`, `ODOO_PASSWORD`
- Do not set `ODOO_ACOPEN_USE_TEST`

## Test

- Set `ODOO_ACOPEN_USE_TEST=1`
- Use `ODOO_ACOPEN_TEST_URL`, `ODOO_ACOPEN_TEST_DB`, `ODOO_ACOPEN_TEST_USER`, `ODOO_ACOPEN_TEST_PASSWORD`

## Rule when the user has not chosen

Ask whether to use **Acopen production** or **Acopen test** before running the operation.

## Optional check

Run:

```bash
python3 {baseDir}/scripts/acopen_env_check.py
```

## References

- `references/env-vars.md`
- `AGENTS.md`
- `TOOLS.md`
