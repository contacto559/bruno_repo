---
name: odoo-recepcion-po
description: List and validate purchase receipts, search by supplier guide folio or vendor bill text. Use for incoming supplier receipts, not outgoing customer GDE.
metadata:
  openclaw:
    requires:
      bins: ["python3"]
      env:
        - "ODOO_URL"
        - "ODOO_USER"
        - "ODOO_PASSWORD"
        - "ODOO_DB"
        - "ODOO_ACOPEN_USE_TEST"
        - "ODOO_ACOPEN_TEST_URL"
        - "ODOO_ACOPEN_TEST_USER"
        - "ODOO_ACOPEN_TEST_PASSWORD"
        - "ODOO_ACOPEN_TEST_DB"
        - "ODOO_ALLOWED_COMPANY_IDS"
        - "ODOO_COMPANY_ID"
---

# Purchase receipts

Use when the user talks about supplier receipts, incoming deliveries, purchase orders, or matching a supplier guide.

## Invocation

```bash
python3 {baseDir}/scripts/odoo_recepcion_po.py <command> [options]
```

## Key rule

Never use this skill for outgoing customer delivery guides. That belongs to `odoo-gde`.

## Reference

Read `RECEPCION_COMPRAS_Y_GDE.md` first.
