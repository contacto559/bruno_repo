#!/usr/bin/env python3
"""
Verifica la conexión Acopen activa: autentica contra el servidor y muestra
el usuario real de la sesión (respetando per-speaker si ODOO_SPEAKER_ID está
exportado en el entorno).
No imprime contraseñas ni API keys.
"""
import os
import sys
import xmlrpc.client
from pathlib import Path

# --- resolver .env del perfil Bruno (busca hacia arriba) ----------------
def _find_env_file(start: Path) -> Path:
    """Walk up the directory tree to find the nearest .env file."""
    for parent in [start, *start.parents]:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    return start / ".env"  # fallback; _parse_env handles FileNotFoundError


_ENV_FILE = _find_env_file(Path(__file__).resolve().parent)


def _parse_env(path: Path) -> dict:
    vals: dict = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return vals


def _env(key: str, file_vals: dict) -> str:
    return os.environ.get(key, "") or file_vals.get(key, "")


USE_TEST_VALUES = ("1", "true", "yes")


def main():
    file_vals = _parse_env(_ENV_FILE)
    use_test = (_env("ODOO_ACOPEN_USE_TEST", file_vals)).strip().lower()

    if use_test in USE_TEST_VALUES:
        url = _env("ODOO_ACOPEN_TEST_URL", file_vals)
        db  = _env("ODOO_ACOPEN_TEST_DB",  file_vals)
        user = _env("ODOO_ACOPEN_TEST_USER", file_vals)
        pwd  = _env("ODOO_ACOPEN_TEST_PASSWORD", file_vals)
        label = "pruebas"
    else:
        url = _env("ODOO_URL", file_vals) or _env("ODOO_ACOPEN_URL", file_vals)
        db  = _env("ODOO_DB",  file_vals) or _env("ODOO_ACOPEN_DB",  file_vals)

        # Per-speaker override (requires ODOO_SPEAKER_ID exported in the shell)
        speaker_id = _env("ODOO_SPEAKER_ID", file_vals)
        user = pwd = ""
        if speaker_id:
            user = _env(f"ODOO_ACOPEN_USER_{speaker_id}", file_vals)
            pwd  = (
                _env(f"ODOO_ACOPEN_APIKEY_{speaker_id}",    file_vals)
                or _env(f"ODOO_ACOPEN_PASSWORD_{speaker_id}", file_vals)
            )

        # Fallback global
        if not user:
            user = _env("ODOO_USER", file_vals) or _env("ODOO_ACOPEN_USER", file_vals)
        if not pwd:
            pwd = _env("ODOO_PASSWORD", file_vals) or _env("ODOO_ACOPEN_PASSWORD", file_vals)

        label = "producción"

    if not url or not db or not user or not pwd:
        print(f"Acopen {label} — faltan variables de entorno (url/db/user/password).")
        sys.exit(1)

    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(db, user, pwd, {})
    except Exception as exc:
        print(f"Acopen {label} — ERROR de red: {exc}")
        sys.exit(1)

    if not uid:
        print(f"Acopen {label} — autenticación fallida para '{user}'. Revisa credenciales.")
        sys.exit(1)

    print(
        f"Acopen {label} — OK\n"
        f"  URL:    {url}\n"
        f"  DB:     {db}\n"
        f"  Usuario de sesión: {user}\n"
        f"  UID:    {uid}"
    )


if __name__ == "__main__":
    main()
