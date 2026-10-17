---
name: acopen-multicompany
description: Mandatory use of allowed_company_ids in all Odoo Acopen operations (multi-company). Use when connecting to Acopen or running queries and writes via XML-RPC.
metadata:
  openclaw:
    requires:
      env:
        - "ODOO_URL"
        - "ODOO_DB"
        - "ODOO_USER"
        - "ODOO_PASSWORD"
        - "ODOO_ALLOWED_COMPANY_IDS"
        - "ODOO_COMPANY_ID"
---

# Acopen multi-company — allowed_company_ids mandatory

Julio only accesses **Acopen**. Acopen is a multi-company environment.

## Fixed rule

Do not query or write to Acopen without including `allowed_company_ids` in the Odoo context whenever the call accepts `context`.

## How to apply

- Include `allowed_company_ids` in all relevant `execute_kw` calls
- Include `company_id` when the action is company-specific
- If the user indicates a specific company, make sure it is inside `allowed_company_ids`

## Summary

- Always pass `allowed_company_ids`
- Include `company_id` when needed
- Without this context, records may appear missing even when the user has access
