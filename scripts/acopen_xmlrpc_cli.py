#!/usr/bin/env python3
"""Acopen XML-RPC CLI for the Bruno profile (read-only).

Credentials: ODOO_ACOPEN_URL/_DB/_USER/_PASSWORD from the project .env.
Default profile: ACOPEN (Main). No create, write, or unlink.
Never prints passwords.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from xmlrpc.client import Fault, ProtocolError, ServerProxy

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT / ".env"
PROFILES = ("ACOPEN", "ACOPEN_TEST")


def parse_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        out[key] = value
    return out


def env_get(key: str, file_vals: dict[str, str]) -> str:
    return (os.environ.get(key) or file_vals.get(key) or "").strip()


def resolve_profile(profile: str, file_vals: dict[str, str]) -> dict[str, str]:
    name = (profile or "ACOPEN").strip().upper().replace("-", "_")
    if name == "ACOPEN_TEST":
        raise ValueError(
            "ACOPEN_TEST is not configured on Sylvia. Use --profile ACOPEN (read-only)."
        )
    if name not in PROFILES:
        raise ValueError(f"Unsupported profile {profile!r}; use ACOPEN")
    url = env_get(f"ODOO_{name}_URL", file_vals)
    db = env_get(f"ODOO_{name}_DB", file_vals)
    user = env_get(f"ODOO_{name}_USER", file_vals)
    password = env_get(f"ODOO_{name}_PASSWORD", file_vals) or env_get(
        f"ODOO_{name}_PASS", file_vals
    )
    missing = [
        k
        for k, v in (
            (f"ODOO_{name}_URL", url),
            (f"ODOO_{name}_DB", db),
            (f"ODOO_{name}_USER", user),
            (f"ODOO_{name}_PASSWORD", password),
        )
        if not v
    ]
    if missing:
        raise ValueError("Missing env keys: " + ", ".join(missing))
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"ODOO_{name}_URL must be http(s)://host")
    return {
        "profile": name,
        "url": url.rstrip("/"),
        "db": db,
        "user": user,
        "password": password,
    }


def out(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def fail(code: int, message: str) -> int:
    out({"ok": False, "error": message})
    return code


def parse_json_arg(name: str, raw: str | None, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{name}: invalid JSON ({exc}). Use double quotes inside JSON, "
            "or prefer --fields id,name on PowerShell."
        ) from exc


def parse_fields(args: argparse.Namespace) -> list[str]:
    """Prefer --fields a,b over --fields-json for PowerShell friendliness."""
    csv = getattr(args, "fields", None) or ""
    if csv.strip():
        return [p.strip() for p in csv.split(",") if p.strip()]
    raw = getattr(args, "fields_json", None) or ""
    fields = parse_json_arg("fields-json", raw, [])
    if fields is not None and not isinstance(fields, list):
        raise ValueError("fields-json must be a JSON list")
    return list(fields or [])


def connect(cfg: dict[str, str]) -> tuple[int, ServerProxy]:
    common = ServerProxy(f"{cfg['url']}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(cfg["db"], cfg["user"], cfg["password"], {})
    if not uid:
        raise RuntimeError("Authentication failed (check user/password for profile)")
    models = ServerProxy(f"{cfg['url']}/xmlrpc/2/object", allow_none=True)
    return int(uid), models


def execute_kw(
    cfg: dict[str, str],
    uid: int,
    models: ServerProxy,
    model: str,
    method: str,
    args: list[Any],
    kwargs: dict[str, Any] | None = None,
) -> Any:
    return models.execute_kw(
        cfg["db"],
        uid,
        cfg["password"],
        model,
        method,
        args,
        kwargs or {},
    )


def cmd_version(cfg: dict[str, str]) -> int:
    common = ServerProxy(f"{cfg['url']}/xmlrpc/2/common", allow_none=True)
    version = common.version()
    out(
        {
            "ok": True,
            "profile": cfg["profile"],
            "url": cfg["url"],
            "db": cfg["db"],
            "server_version": version.get("server_version"),
            "version": version,
        }
    )
    return 0


def cmd_auth(cfg: dict[str, str]) -> int:
    uid, _ = connect(cfg)
    out(
        {
            "ok": True,
            "profile": cfg["profile"],
            "url": cfg["url"],
            "db": cfg["db"],
            "uid": uid,
            "user": cfg["user"],
        }
    )
    return 0


def cmd_search_read(cfg: dict[str, str], args: argparse.Namespace) -> int:
    domain = parse_json_arg("domain-json", args.domain_json, [])
    fields = parse_fields(args)
    context = parse_json_arg("context-json", args.context_json, {})
    if not isinstance(domain, list):
        raise ValueError("domain-json must be a JSON list")
    if context is not None and not isinstance(context, dict):
        raise ValueError("context-json must be a JSON object")
    uid, models = connect(cfg)
    kw: dict[str, Any] = {
        "limit": args.limit,
        "offset": args.offset,
    }
    if fields:
        kw["fields"] = fields
    if args.order:
        kw["order"] = args.order
    if context:
        kw["context"] = context
    rows = execute_kw(cfg, uid, models, args.model, "search_read", [domain], kw)
    out(
        {
            "ok": True,
            "profile": cfg["profile"],
            "model": args.model,
            "count": len(rows) if isinstance(rows, list) else None,
            "records": rows,
        }
    )
    return 0


def cmd_read(cfg: dict[str, str], args: argparse.Namespace) -> int:
    ids = parse_json_arg("ids-json", args.ids_json, None)
    fields = parse_fields(args)
    if not isinstance(ids, list) or not ids:
        raise ValueError("ids-json must be a non-empty JSON list of ids")
    uid, models = connect(cfg)
    kw: dict[str, Any] = {}
    if fields:
        kw["fields"] = fields
    rows = execute_kw(cfg, uid, models, args.model, "read", [ids], kw)
    out(
        {
            "ok": True,
            "profile": cfg["profile"],
            "model": args.model,
            "records": rows,
        }
    )
    return 0


def cmd_fields_get(cfg: dict[str, str], args: argparse.Namespace) -> int:
    uid, models = connect(cfg)
    attrs = parse_json_arg(
        "attributes-json",
        args.attributes_json,
        ["string", "type", "required", "readonly", "relation"],
    )
    data = execute_kw(
        cfg,
        uid,
        models,
        args.model,
        "fields_get",
        [],
        {"attributes": attrs} if attrs else {},
    )
    out({"ok": True, "profile": cfg["profile"], "model": args.model, "fields": data})
    return 0


def _common_args() -> argparse.ArgumentParser:
    """Shared flags so `cmd --profile X` matches Bender CLI style."""
    c = argparse.ArgumentParser(add_help=False)
    c.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    c.add_argument(
        "--profile",
        default="ACOPEN",
        help="ACOPEN (Main, read-only). ACOPEN_TEST is not configured.",
    )
    c.add_argument("--timeout-seconds", type=float, default=30.0)
    return c


def build_parser() -> argparse.ArgumentParser:
    common = _common_args()
    p = argparse.ArgumentParser(description="Bruno Acopen XML-RPC CLI (read-only)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("version", parents=[common], help="common.version() without auth")
    sub.add_parser("auth", parents=[common], help="authenticate and print uid")

    sr = sub.add_parser("search_read", parents=[common], help="ORM search_read")
    sr.add_argument("--model", required=True)
    sr.add_argument("--domain-json", default="[]")
    sr.add_argument("--fields", default="", help="Comma-separated fields (preferred on Windows)")
    sr.add_argument("--fields-json", default="")
    sr.add_argument("--context-json", default="")
    sr.add_argument("--limit", type=int, default=20)
    sr.add_argument("--offset", type=int, default=0)
    sr.add_argument("--order", default="")

    rd = sub.add_parser("read", parents=[common], help="ORM read by ids")
    rd.add_argument("--model", required=True)
    rd.add_argument("--ids-json", required=True)
    rd.add_argument("--fields", default="", help="Comma-separated fields (preferred on Windows)")
    rd.add_argument("--fields-json", default="")

    fg = sub.add_parser("fields_get", parents=[common], help="fields_get metadata")
    fg.add_argument("--model", required=True)
    fg.add_argument("--attributes-json", default="")

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    socket.setdefaulttimeout(args.timeout_seconds)
    try:
        file_vals = parse_env_file(args.env_file.resolve())
        cfg = resolve_profile(args.profile, file_vals)
        if args.command == "version":
            return cmd_version(cfg)
        if args.command == "auth":
            return cmd_auth(cfg)
        if args.command == "search_read":
            return cmd_search_read(cfg, args)
        if args.command == "read":
            return cmd_read(cfg, args)
        if args.command == "fields_get":
            return cmd_fields_get(cfg, args)
        return fail(2, f"Unknown command {args.command}")
    except ValueError as exc:
        return fail(2, str(exc))
    except (ProtocolError, Fault) as exc:
        return fail(4, f"XML-RPC error: {exc}")
    except OSError as exc:
        return fail(4, f"Network error: {exc}")
    except RuntimeError as exc:
        return fail(3, str(exc))


if __name__ == "__main__":
    sys.exit(main())
