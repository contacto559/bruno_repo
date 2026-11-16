#!/usr/bin/env python3
"""Shared Acopen XML-RPC connection helper for Bruno skills.

Credential resolution order per call (first non-empty wins):
  1. ODOO_ACOPEN_USER_<ODOO_SPEAKER_ID> + ODOO_ACOPEN_APIKEY_<id>
     or ODOO_ACOPEN_PASSWORD_<id>  (per-speaker, applied when ODOO_SPEAKER_ID is set)
  2. ODOO_USER / ODOO_PASSWORD   (alias block in .env)
  3. ODOO_ACOPEN_USER / ODOO_ACOPEN_PASSWORD  (canonical block in .env)

Company context:
  Each speaker authenticates as themselves. get_company_context() returns {}
  so Odoo applies that user's own companies. Do not force a company.

Never prints passwords or secrets.
"""
from __future__ import annotations

import os
import xmlrpc.client
from pathlib import Path

# skills/shared/acopen_rpc.py → parents[0]=shared, [1]=skills, [2]=bruno_repo root
ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = ROOT / ".env"

def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in {"'", '"'}:
            v = v[1:-1]
        out[k] = v
    return out


def _env(key: str, file_vals: dict[str, str]) -> str:
    return (os.environ.get(key) or file_vals.get(key) or "").strip()


def get_connection():
    """Return (db, uid, password, models_proxy) ready for execute_kw."""
    file_vals = _parse_env(_ENV_FILE)

    url = _env("ODOO_URL", file_vals) or _env("ODOO_ACOPEN_URL", file_vals)
    db  = _env("ODOO_DB",  file_vals) or _env("ODOO_ACOPEN_DB",  file_vals)

    # Per-speaker override when ODOO_SPEAKER_ID is in the environment
    speaker_id = _env("ODOO_SPEAKER_ID", file_vals)
    user = pwd = ""
    if speaker_id:
        user = _env(f"ODOO_ACOPEN_USER_{speaker_id}", file_vals)
        pwd  = (
            _env(f"ODOO_ACOPEN_APIKEY_{speaker_id}",    file_vals)
            or _env(f"ODOO_ACOPEN_PASSWORD_{speaker_id}", file_vals)
        )

    # Fall back to shared defaults
    if not user:
        user = _env("ODOO_USER", file_vals) or _env("ODOO_ACOPEN_USER", file_vals)
    if not pwd:
        pwd = _env("ODOO_PASSWORD", file_vals) or _env("ODOO_ACOPEN_PASSWORD", file_vals)

    missing = [k for k, v in (("ODOO_URL", url), ("ODOO_DB", db),
                               ("ODOO_USER", user), ("ODOO_PASSWORD", pwd)) if not v]
    if missing:
        raise RuntimeError(
            "Acopen no disponible en este momento. "
            f"(missing: {', '.join(missing)})"
        )

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(db, user, pwd, {})
    if not uid:
        raise RuntimeError(
            "Acopen: autenticación fallida. "
            "Verifica usuario y contraseña."
        )
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
    return db, int(uid), pwd, models


def get_company_context(speaker_id: str | int | None = None) -> dict:
    """Return empty dict; Odoo applies the authenticated user's companies."""
    return {}


def execute_kw(models, db, uid, password, model, method, args, kw=None):
    """Thin wrapper — same signature as the direct XML-RPC call."""
    return models.execute_kw(db, uid, password, model, method, args, kw or {})
