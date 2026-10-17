# Acopen environment variables

Credentials and URLs are read only from environment files.

## Production

- `ODOO_URL`
- `ODOO_DB`
- `ODOO_USER`
- `ODOO_PASSWORD`

## Test

- `ODOO_ACOPEN_TEST_URL`
- `ODOO_ACOPEN_TEST_DB`
- `ODOO_ACOPEN_TEST_USER`
- `ODOO_ACOPEN_TEST_PASSWORD`

## Convention

- Use `ODOO_ACOPEN_USE_TEST=1` when the user has chosen test
- Do not set it when the user has chosen production

## Logistics Drive (skill `odoo-picking-drive-link`)

- `JULIO_GDRIVE_LOGISTICS_CONSOLE_ID` — `google.console` id for PENTAGON (recommended)
- `JULIO_GDRIVE_LOGISTICS_CONSOLE_NAME` — exact `name` on `google.console` if id is not set
- `JULIO_GDRIVE_LOGISTICS_FOLDER_ID` — optional override for the Drive parent folder
- `ODOO_STOCK_PICKING_REPORT_PREFERRED` — comma-separated `report_name` fallbacks for PDF generation
