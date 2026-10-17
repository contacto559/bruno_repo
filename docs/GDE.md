<!-- Reference copy from workspace-julio. VPS paths in this file are Julio runtime, not Bruno. Bruno credentials live in this workspace .env. -->

# Electronic Delivery Guide (GDE)

This file is a support summary. The inviolable rule set for reception and delivery tasks is `PAUTAS_INVIOLABLES_RECEPCIONES_ENTREGAS_ACOPEN.md`.

**Scope:** customer shipments only. For supplier receipts and purchase orders, use `RECEPCION_COMPRAS_Y_GDE.md` and `skills/odoo-recepcion-po/SKILL.md`.

## What the GDE is

An electronic tax document that certifies the movement of goods in Chile and is sent to the SII.

## Preconditions

- Picking must be `done`
- Picking must be **outgoing**
- Company must be configured for Chile and SII
- A valid CAF for document type 52 must exist
- Partner delivery data must be complete

If any of these fail, Odoo will reject the flow.

## REGLA INVIOLABLE — No recrear guía ya aceptada

> Esta regla no tiene excepciones. No existe ninguna razón válida para ejecutar `create_delivery_guide()` sobre una guía ya aceptada u objetada.

**Antes de cualquier acción**, leer `l10n_cl_dte_status` del picking:

| `l10n_cl_dte_status` | Acción correcta |
|----------------------|-----------------|
| `accepted` o `objected` | **PROHIBIDO** ejecutar `create_delivery_guide`. Solo imprimir con `print_delivery_guide_pdf()` y descargar PDF por sesión web. |
| `ask_for_status` | No recrear. Verificar con `l10n_cl_verify_dte_status()`. Para PDF: usar `print_delivery_guide_pdf()`. |
| `not_sent`, `rejected`, `cancelled`, vacío | Flujo normal (paso 1 de abajo). |

**Por qué**: `create_delivery_guide()` siempre resetea `l10n_cl_dte_status='not_sent'`, regenera el DTE y destruye los adjuntos legales del SII. Ejecutarlo sobre una guía aceptada la convierte en rechazada.

## Issuance steps

| Step | Action | Odoo method |
|------|--------|-------------|
| 0 | **Leer estado SII** (ver regla inviolable arriba) | `read(['l10n_cl_dte_status'])` |
| 1 | Create guide (solo si NO está accepted/objected) | `create_delivery_guide()` |
| 2 | Send to SII | `l10n_cl_send_dte_to_sii()` |
| 3 | Verify SII status | `l10n_cl_verify_dte_status()` |
| 4 | Print PDF | `print_delivery_guide_pdf()` |

## SII states

- `not_sent`
- `ask_for_status`
- `accepted`
- `objected`
- `rejected`
- `cancelled`
- `manual`

## Use from Julio

- Identify the outgoing picking by ID or by name such as `WH/OUT/00042`
- Confirm before each state-changing step
- Reply in plain language unless the user asks for technical detail

## Matching skill

Use `skills/odoo-gde/SKILL.md` for the executable CLI flow.

## Drive archive + `google.drive.link` (optional)

When the user wants the guide (or another picking PDF) stored in **logistics Google Drive** and linked on the picking:

1. Complete the usual GDE steps as needed (`create` / `send` / `verify` / `print`).
2. Obtain **explicit confirmation** (see `AGENTS.md` → Confirmation detail).
3. Run **`skills/odoo-picking-drive-link/SKILL.md`** with `--picking` and `--yes` (default: generates a PDF from a `stock.picking` QWeb report, or use `--file` if the document is already on disk). Reply with **`picking_form_url`** and the Drive link from the script JSON.
