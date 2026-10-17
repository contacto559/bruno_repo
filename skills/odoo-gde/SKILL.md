---
name: odoo-gde
description: Create, send to SII, verify status, and print delivery guides for Chilean outgoing customer pickings only.
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

# Odoo GDE

**Outgoing / sales only.** For purchase receipts use `odoo-recepcion-po`.

## REGLA INVIOLABLE — Guard por estado SII

**Antes de `create` (y antes de cualquier otra operación)**, consultar el estado con `status` y aplicar:

| `l10n_cl_dte_status` | Acción permitida |
|----------------------|-----------------|
| `accepted` o `objected` | **PROHIBIDO** `create`. Usar solo `print` para obtener el PDF. |
| `ask_for_status` | No recrear. Usar `verify` para consultar SII. |
| `not_sent`, `rejected`, `cancelled`, vacío | Se puede ejecutar `create`. |

Ejecutar `create` sobre una guía aceptada la destruye (resetea estado, borra DTE firmado). El script ya implementa este guard: bloquea con error si el estado es `accepted` u `objected`.

## When to use

- Create a guide for an outgoing picking already in `done` **and NOT yet accepted/objected**
- Send guide to SII
- Verify SII status
- Print the guide PDF (including for already-accepted guides)
- Read current guide status

## Invocation

```bash
python3 {baseDir}/scripts/odoo_gde.py <operation> --picking <id_or_name> [options]
```

## Reference

Read `GDE.md` first.
