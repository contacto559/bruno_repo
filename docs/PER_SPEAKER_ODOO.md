# Per-speaker Odoo credentials (Bruno)

Bruno no usa una sola cuenta de Odoo para todos. Cada speaker de Telegram autentica
con su propio usuario (o con admin si no hay override). Las reglas nativas de Odoo
(`ir.rule`, compañías, grupos) aplican sobre esa sesión XML-RPC.

JR no es Juan Romero. JR (`684058204`) es IT / administrador. Juan Romero
(`9059457598`) es bodega Pentagon.

## Mapa

| Telegram id | Persona | Odoo login | Env vars | Rol |
|-------------|---------|------------|----------|-----|
| `684058204` | JR | `admin@acomin.cl` | `ODOO_ACOPEN_USER_684058204` + `ODOO_ACOPEN_APIKEY_684058204` | Admin, tres empresas |
| `9059457598` | Juan Romero | `jromero@pentagon.cl` | `ODOO_ACOPEN_USER_9059457598` + `ODOO_ACOPEN_APIKEY_9059457598` | Bodega, solo Pentagon |
| `6290405799` | Sebastián Briones | `sbriones@acomin.cl` | `ODOO_ACOPEN_USER_6290405799` + `ODOO_ACOPEN_APIKEY_6290405799` | Bodega, solo Pentagon |
| otros (Matías, Israel, Marco) | IT / fallback | `ODOO_ACOPEN_USER` | `ODOO_ACOPEN_PASSWORD` | Admin (fallback) |

Las keys viven solo en `.env` (gitignored). No se commitean ni se pegan en chat.

## Cómo se resuelven

1. El bridge inyecta el Telegram user id en el prompt (`prompt_wrapper.py`).
2. El agente prepende `ODOO_SPEAKER_ID=<id>` a cada script Odoo.
3. `scripts/acopen_xmlrpc_cli.py` (`--speaker-id` o `ODOO_SPEAKER_ID`) y
   `skills/shared/acopen_rpc.py` leen:
   - `ODOO_ACOPEN_USER_<id>`
   - `ODOO_ACOPEN_APIKEY_<id>` (o `ODOO_ACOPEN_PASSWORD_<id>`)
4. Si no hay override, caen a `ODOO_ACOPEN_USER` / `ODOO_ACOPEN_PASSWORD`.
5. `scripts/acopen_download_report_pdf.py` también acepta `--speaker-id`.

Skills GDE y recepción (`odoo-gde`, `odoo-recepcion-po`) usan
`skills/shared/acopen_rpc.py`, así que heredan el mismo mapa.

## Cómo se generan las keys

Módulo Odoo `admin_apikey_manager` (Acopennova, `internos17`, commit `04c86717`):

Settings → Technical → Claves API de administrador → Generar clave API.

El admin genera la key a nombre de cualquier usuario interno con
`res.users.apikeys.with_user(target)._generate()`. No cambia la contraseña
web del trabajador. La key se muestra una sola vez (campo Text, 40 hex).

Para JR se usa `admin@acomin.cl` + su API key (no `lelouchvibritannia@gmail.com`
en el override per-speaker). El fallback global del `.env` sigue siendo
`lelouchvibritannia@gmail.com` para speakers sin override.

## Prueba (host Bruno)

```bash
cd ~/repos/bruno_repo
ODOO_SPEAKER_ID=684058204 python3 scripts/acopen_xmlrpc_cli.py auth
# uid admin (admin@acomin.cl)

ODOO_SPEAKER_ID=9059457598 python3 scripts/acopen_xmlrpc_cli.py auth
# uid 106, jromero@pentagon.cl

ODOO_SPEAKER_ID=6290405799 python3 scripts/acopen_xmlrpc_cli.py auth
# uid 94, sbriones@acomin.cl
```

Nunca imprimir la key ni el password.

## Qué no hacer

- No resetear contraseñas de trabajadores.
- No crear un usuario extra de Odoo (cupo SaaS).
- No commitear `.env`.
- No pedirles a Juan o Sebastián que generen la key: el admin la genera.
