# USER.md

People reach Bruno through the Telegram bot for this machine. Only ids in `ALLOWED_TELEGRAM_USER_IDS` are answered.

| Speaker | Role | Company access | Odoo login (XML-RPC) |
|---------|------|----------------|----------------------|
| JR (`684058204`) | IT / admin | PENTAGON, ACOMIN, NOVATEX | `admin@acomin.cl` (API key) |
| Matías (`7101490437`) | IT | PENTAGON, ACOMIN, NOVATEX | fallback admin |
| Israel (`8409454444`) | IT | PENTAGON, ACOMIN, NOVATEX | fallback admin |
| Sebastián Briones (`6290405799`, +56949273810) | Warehouse | PENTAGON only | `sbriones@acomin.cl` (API key) |
| Marco Jara (`7164957786`, +56958405293) | Warehouse | PENTAGON only | fallback admin (cuenta Odoo inactiva) |
| Juan Romero (`9059457598`, +56942276622) | Warehouse | PENTAGON only | `jromero@pentagon.cl` (API key) |

Warehouse speakers (Sebastián, Marco, Juan) always use PENTAGON (`company_id=1`, `allowed_company_ids=[1]`). Do not ask which company; do not show ACOMIN or NOVATEX records to them.

Do not repeat ids or phone numbers in a user-facing reply. Do not invent a person's name. Use the name they give in the chat.
