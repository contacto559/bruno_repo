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

Read `stock` and, when the document is Chilean, `l10n_cl` under `/home/bruno-polypus/bruno_ project/odoo_17/addons` before naming a field. That tree is Odoo `17.0+e.20260310`. If this skill and that code disagree, the code wins.

Use when the user talks about supplier receipts, incoming deliveries, purchase orders, or matching a supplier guide.

## Invocation

```bash
python3 {baseDir}/scripts/odoo_recepcion_po.py <command> [options]
```

## Key rule

Never use this skill for outgoing customer delivery guides. That belongs to `odoo-gde`.

## Reference

Read `RECEPCION_COMPRAS_Y_GDE.md` first.
