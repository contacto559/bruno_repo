<!-- Reference copy from workspace-julio. VPS paths in this file are Julio runtime, not Bruno. Bruno credentials live in this workspace .env. -->

# Purchase receipts vs sales delivery guides

This file is a support summary. The inviolable rule set for reception and delivery tasks is `PAUTAS_INVIOLABLES_RECEPCIONES_ENTREGAS_ACOPEN.md`.

This note tells Julio how to separate two different situations and what to do in each.

## Code locations

| Path | Contents |
|------|----------|
| `/root/acopen-repo` | Acopen custom modules and business logic |
| `/root/odoo-base` | Odoo standard addons |

## A. Sales: delivery to the customer

- This is an **outgoing** shipment to a customer
- Typical picking names look like `WH/OUT/...`
- The matching tool is `odoo-gde`
- This is where an electronic delivery guide (GDE) can be created, sent, verified, and printed

Do not use this flow for supplier receipts.

## B. Purchase: receipt from a supplier

- This is an **incoming** receipt against a purchase order
- Typical picking names look like `WH/IN/...`
- The matching tool is `odoo-recepcion-po`
- If the user mentions a supplier guide number, the goal is usually to match it to an incoming receipt or vendor bill, not to create a customer GDE

### Form 1 - Invoice first

1. Supplier invoice is entered
2. Purchase order is generated or identified from that invoice
3. Products are normalized so PO lines match the real items
4. The PO is confirmed
5. Incoming receipts are validated when goods are physically received

### Form 2 - Supplier guide first

1. Search an incoming receipt by supplier, dates, PO reference, or folio
2. If no receipt is found, search vendor bills by the guide reference
3. If an invoice is found and the receipt flow is not yet clear, return to Form 1

## Quick decision table

| User says | Treat as | Main tool |
|-----------|----------|-----------|
| Guide for customer / sale / `WH/OUT` | Outgoing customer delivery | `odoo-gde` |
| Receive PO / supplier delivery / `WH/IN` | Incoming supplier receipt | `odoo-recepcion-po` |
| Guide number but unclear context | Ask whether goods are going out to a customer or coming in from a supplier | Clarify first |

## Acopen-only and multicompany

All XML-RPC operations here are Acopen-only and must respect:

- production or test chosen by the user
- `allowed_company_ids` in context
- `company_id` when a company-specific action requires it

## Drive archive after validating a receipt

If the user asks to file the receipt document in **Google Drive** and register it on the picking:

1. Use `skills/odoo-recepcion-po/SKILL.md` for validation (`validate` + `--yes`) after confirmation.
2. Confirm again if chaining Drive upload (PENTAGON console, logistics folder — see `PAUTA_GOOGLE_DRIVE.md`).
3. Run **`skills/odoo-picking-drive-link/SKILL.md`** with the same picking (`--file` if they provided a path on the server, else PDF from Odoo report). Always include **`picking_form_url`** in the reply.
