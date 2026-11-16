# USER.md

People reach Bruno through the Telegram bot for this machine. Only ids in `ALLOWED_TELEGRAM_USER_IDS` are answered.

| Speaker | Role | Company access | Odoo login (XML-RPC) |
|---------|------|----------------|----------------------|
| JR (`684058204`) | IT / admin | The companies on `admin@acomin.cl` | `admin@acomin.cl` (API key) |
| Matías (`7101490437`) | IT | Same as the fallback admin | fallback admin |
| Israel (`8409454444`) | IT | Same as the fallback admin | fallback admin |
| Sebastián Briones (`6290405799`, +56949273810) | Warehouse | ACOMIN only (his Odoo record) | `sbriones@acomin.cl` (API key) |
| Marco Jara (`7164957786`, +56958405293) | Warehouse | Same as the fallback admin | fallback admin (cuenta Odoo inactiva) |
| Juan Romero (`9059457598`, +56942276622) | Warehouse | PENTAGON and ACOMIN (his Odoo record) | `jromero@pentagon.cl` (API key) |

Do not force a company in code. Odoo already limits each login to the companies on that user.

Do not repeat ids or phone numbers in a user-facing reply. Do not invent a person's name. Use the name they give in the chat.
