---
name: odoo17-chile
description: >-
  Read Odoo 17 enterprise source before any Odoo task. Chilean localization
  (l10n_cl, SII, DTE) is mandatory. Use before writing or answering anything
  about invoices, taxes, boletas, partners, pickings, or delivery guides.
---

# Odoo 17 enterprise source (Chile)

Package on this machine: `odoo_17.0+e.20260310_all.deb`.

Source tree (modules extracted from that package):

`/home/bruno-polypus/bruno_ project/odoo_17/addons`

Same tree via the workspace symlink: `~/repos/bruno_repo/odoo_17/addons`.

The `.deb` stays next to that folder. Do not delete it. Do not invent a newer Odoo.

## Rule

Before any Odoo task, open the module you will use in that tree. Field names, states, buttons, and method names come from those files. If a skill, a memory, or an old document disagrees with this tree, this tree wins.

New skills must be written from this code. Do not describe a flow that is not in the module.

## Chilean localization first

When the task touches taxes, invoices, boletas, credit notes, RUT, CAF, DTE, the SII, or an electronic delivery guide, read these modules before answering:

- `l10n_cl`
- `l10n_cl_edi`
- `l10n_cl_edi_boletas`
- `l10n_latam_invoice_document`

Confirm selection values in the model (for example `l10n_cl_dte_status`) before using them. Do not invent SII states or tax tags. Never call `create_delivery_guide` when `l10n_cl_dte_status` is `accepted` or `objected`.
