#!/usr/bin/env python3
"""Download Odoo 17 QWeb PDF (read-only) using the Bruno project .env.

XML-RPC resolve ir.actions.report → POST /web/session/authenticate →
GET /web?db= (CSRF) → GET /report/pdf → fallback POST /report/download → assert %PDF-.

Never use /xmlrpc/2/report or /web/authenticate. Never print passwords.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import xmlrpc.client
from pathlib import Path

try:
    import requests
except ImportError:
    print(
        json.dumps({"ok": False, "error": "Install requests (requirements-bridge.txt)"}),
        file=sys.stderr,
    )
    sys.exit(1)

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from acopen_xmlrpc_cli import DEFAULT_ENV, ROOT, parse_env_file, resolve_profile  # noqa: E402

DEFAULT_PREFERRED_SALE = "sale.report_saleorder_raw,sale.report_saleorder"
OUTBOUND = ROOT / "media" / "outbound"


def out(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def rpc_auth(base_url: str, db: str, login: str, password: str):
    common = xmlrpc.client.ServerProxy(
        f"{base_url}/xmlrpc/2/common", allow_none=True
    )
    uid = common.authenticate(db, login, password, {})
    if not uid:
        raise RuntimeError("XML-RPC authenticate failed")
    models = xmlrpc.client.ServerProxy(
        f"{base_url}/xmlrpc/2/object", allow_none=True
    )
    return int(uid), models


def resolve_record_ids(
    models,
    db: str,
    uid: int,
    password: str,
    model: str,
    res_id: int | None,
    name_field: str,
    name_value: str | None,
    domain_json: str | None,
    order: str,
    limit: int,
) -> list[int]:
    if res_id is not None:
        return [res_id]
    domain: list = []
    if domain_json:
        domain = json.loads(domain_json)
        if not isinstance(domain, list):
            raise ValueError("domain-json must be a list")
    elif name_value:
        domain.append((name_field, "=", name_value.strip()))
    else:
        raise ValueError("Provide --res-id, --name-value, or --domain-json")
    ids = models.execute_kw(
        db,
        uid,
        password,
        model,
        "search",
        [domain],
        {"order": order, "limit": limit + 1},
    )
    if not ids:
        raise RuntimeError(f"No {model} for domain {domain!r}")
    if len(ids) > limit:
        raise RuntimeError(f"More than {limit} matches; narrow the domain")
    return list(ids[:limit])


def pick_report(
    models,
    db: str,
    uid: int,
    password: str,
    model: str,
    report_type: str,
    report_name_override: str | None,
    preferred_csv: str,
) -> tuple[str, str]:
    if report_name_override:
        rep_ids = models.execute_kw(
            db,
            uid,
            password,
            "ir.actions.report",
            "search",
            [[("model", "=", model), ("report_name", "=", report_name_override)]],
            {"limit": 5},
        )
        if not rep_ids:
            raise RuntimeError(
                f"No ir.actions.report report_name={report_name_override!r} for {model}"
            )
        reps = models.execute_kw(
            db,
            uid,
            password,
            "ir.actions.report",
            "read",
            [rep_ids],
            {"fields": ["name", "report_name", "report_type"]},
        )
        r = reps[0]
        if r.get("report_type") != report_type:
            raise RuntimeError(
                f"Report type {r.get('report_type')!r} != {report_type!r}"
            )
        return r["report_name"], r["name"]

    rep_ids = models.execute_kw(
        db,
        uid,
        password,
        "ir.actions.report",
        "search",
        [[("model", "=", model), ("report_type", "=", report_type)]],
        {"limit": 40},
    )
    if not rep_ids:
        raise RuntimeError(f"No ir.actions.report {report_type} for {model}")
    reps = models.execute_kw(
        db,
        uid,
        password,
        "ir.actions.report",
        "read",
        [rep_ids],
        {"fields": ["name", "report_name", "report_type"]},
    )
    by_rn = {x["report_name"]: x for x in reps}
    preferred = [x.strip() for x in preferred_csv.split(",") if x.strip()]
    if model == "sale.order" and not preferred:
        preferred = DEFAULT_PREFERRED_SALE.split(",")
    for rn in preferred:
        if rn in by_rn:
            return by_rn[rn]["report_name"], by_rn[rn]["name"]
    r0 = reps[0]
    return r0["report_name"], r0["name"]


def web_session_and_csrf(base_url: str, db: str, login: str, password: str):
    s = requests.Session()
    auth_url = f"{base_url}/web/session/authenticate"
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "id": 1,
        "params": {"db": db, "login": login, "password": password},
    }
    r = s.post(
        auth_url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=90,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("error"):
        raise RuntimeError(f"authenticate: {body['error']}")
    if not s.cookies.get("session_id"):
        raise RuntimeError("No session_id cookie after authenticate")
    r2 = s.get(f"{base_url}/web", params={"db": db}, timeout=90, allow_redirects=True)
    r2.raise_for_status()
    m = re.search(r'csrf_token:\s*"([^"]+)"', r2.text)
    if not m:
        raise RuntimeError("csrf_token not found in /web HTML")
    return s, m.group(1)


def try_get_pdf(session, base_url: str, db: str, report_name: str, res_id: int):
    url = f"{base_url}/report/pdf/{report_name}/{res_id}"
    return session.get(url, params={"db": db}, timeout=180)


def post_download(
    session, base_url: str, db: str, csrf: str, report_name: str, res_id: int, rt: str
):
    internal = f"/report/pdf/{report_name}/{res_id}"
    data = {
        "data": json.dumps([internal, rt]),
        "token": "dummy-because-api-expects-one",
        "csrf_token": csrf,
    }
    return session.post(
        f"{base_url}/report/download",
        params={"db": db},
        data=data,
        timeout=180,
    )


def assert_pdf(content: bytes) -> None:
    if not content or len(content) < 5 or not content.startswith(b"%PDF-"):
        head = (content or b"")[:80]
        raise RuntimeError(f"Not a PDF (magic != %PDF-). head={head!r}")


def copy_outbound(src: Path, filename: str) -> Path:
    OUTBOUND.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w.\-]+", "_", filename)[:120] or "odoo_report.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    dest = OUTBOUND / name
    shutil.copy2(src, dest)
    return dest.resolve()


def cmd_download(args: argparse.Namespace) -> int:
    file_vals = parse_env_file(Path(args.env_file).resolve())
    cfg = resolve_profile(args.profile, file_vals)
    uid, models = rpc_auth(cfg["url"], cfg["db"], cfg["user"], cfg["password"])
    res_ids = resolve_record_ids(
        models,
        cfg["db"],
        uid,
        cfg["password"],
        args.model,
        args.res_id,
        args.name_field,
        args.name_value,
        args.domain_json,
        args.order,
        args.limit,
    )
    preferred = args.preferred_reports or ""
    if args.model == "sale.order" and not preferred:
        preferred = DEFAULT_PREFERRED_SALE
    report_name, report_title = pick_report(
        models,
        cfg["db"],
        uid,
        cfg["password"],
        args.model,
        args.report_type,
        args.report_name,
        preferred,
    )

    label = args.name_value or str(res_ids[0])
    safe = re.sub(r"[^\w\-.]+", "_", f"{args.model}_{label}")[:80]
    out_path = Path(args.output) if args.output else (OUTBOUND / f"odoo_report_{safe}.pdf")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    session, csrf = web_session_and_csrf(
        cfg["url"], cfg["db"], cfg["user"], cfg["password"]
    )
    method_used = "POST"
    r = try_get_pdf(session, cfg["url"], cfg["db"], report_name, res_ids[0])
    if r.status_code == 200 and r.headers.get("Content-Type", "").startswith(
        "application/pdf"
    ):
        method_used = "GET"
        content = r.content
    else:
        r2 = post_download(
            session,
            cfg["url"],
            cfg["db"],
            csrf,
            report_name,
            res_ids[0],
            args.report_type,
        )
        r2.raise_for_status()
        content = r2.content
        method_used = "POST"

    assert_pdf(content)
    out_path.write_bytes(content)

    deliver_filename = (args.deliver_filename or "").strip() or (
        f"{label}_{res_ids[0]}.pdf"
    )
    if not deliver_filename.lower().endswith(".pdf"):
        deliver_filename += ".pdf"
    outbound = copy_outbound(out_path, deliver_filename)

    env_label = "Pruebas" if cfg["profile"] == "ACOPEN_TEST" else "Produccion"
    kind = {
        "sale.order": "Orden",
        "stock.picking": "Albaran",
        "account.move": "Factura",
        "crm.lead": "Oportunidad",
    }.get(args.model, "Documento")
    caption = args.deliver_caption or f"{kind} {label} — {env_label}"
    telegram_line = f"TELEGRAM_DOCUMENT: {outbound} | {caption}"

    result = {
        "ok": True,
        "output_path": str(out_path.resolve()),
        "outbound_path": str(outbound),
        "bytes": len(content),
        "model": args.model,
        "res_ids": res_ids,
        "report_name": report_name,
        "report_title": report_title,
        "method": method_used,
        "profile": cfg["profile"],
        "url": cfg["url"],
        "db": cfg["db"],
        "telegram_line": telegram_line,
        "caption": caption,
        "next_step": (
            "Put telegram_line alone in the final assistant message "
            "(plus a short Spanish caption). The Telegram bridge will attach the PDF."
        ),
    }
    out(result)
    print(telegram_line, file=sys.stderr)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Bruno: download Odoo QWeb PDF")
    p.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download", help="Download PDF for one record")
    d.add_argument("--profile", default="ACOPEN")
    d.add_argument("--model", required=True)
    d.add_argument("--res-id", type=int, default=None)
    d.add_argument("--name-field", default="name")
    d.add_argument("--name-value", default=None)
    d.add_argument("--domain-json", default=None)
    d.add_argument("--order", default="id desc")
    d.add_argument("--limit", type=int, default=1)
    d.add_argument("--report-type", default="qweb-pdf")
    d.add_argument("--report-name", default=None)
    d.add_argument("--preferred-reports", default=None)
    d.add_argument("-o", "--output", default=None)
    d.add_argument("--deliver-filename", default=None)
    d.add_argument("--deliver-caption", default=None)
    args = p.parse_args()
    if args.cmd != "download":
        return 2
    try:
        return cmd_download(args)
    except Exception as exc:  # noqa: BLE001
        out({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
