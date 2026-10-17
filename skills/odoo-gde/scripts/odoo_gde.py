#!/usr/bin/env python3
"""
Odoo GDE (Guia de Despacho Electronica) CLI.
Creates, sends to SII, verifies status and prints delivery guides for Chilean pickings.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import xmlrpc.client

sys.path.append(str(Path(__file__).resolve().parents[2]))
from shared.acopen_rpc import execute_kw, get_connection


def resolve_picking(db, uid, password, object_, picking_ref):
    try:
        pid = int(picking_ref)
        ids = execute_kw(object_, db, uid, password, "stock.picking", "search", [[["id", "=", pid]]], {"limit": 1})
        if ids:
            return ids[0]
        raise SystemExit(f"Error: no se encontro picking con ID {picking_ref}")
    except ValueError:
        pass
    ids = execute_kw(object_, db, uid, password, "stock.picking", "search", [[["name", "=", picking_ref]]], {"limit": 1})
    if not ids:
        raise SystemExit(f"Error: no se encontro picking con nombre '{picking_ref}'")
    return ids[0]


GUARD_STATUSES = ("accepted", "objected")


def run_create(db, uid, password, object_, picking_id, json_out):
    # GUARD INVIOLABLE: leer l10n_cl_dte_status antes de ejecutar create_delivery_guide.
    # Si la guía ya está aceptada u objetada, ejecutarla la destruye (resetea estado,
    # borra el DTE firmado y adjuntos legales). El resultado es una guía rechazada.
    rows = execute_kw(object_, db, uid, password, "stock.picking", "read",
                      [[picking_id]], {"fields": ["name", "l10n_cl_dte_status", "l10n_latam_document_number"]})
    if not rows:
        raise SystemExit(f"Error: picking id={picking_id} no encontrado.")
    pk = rows[0]
    dte_status = pk.get("l10n_cl_dte_status") or ""
    if dte_status in GUARD_STATUSES:
        msg = (
            f"BLOQUEADO (REGLA INVIOLABLE): la guia {pk.get('name')} ya esta {dte_status} "
            f"(folio: {pk.get('l10n_latam_document_number') or '-'}). "
            f"No se puede ejecutar create_delivery_guide sobre una guia ya aprobada — "
            f"use la operacion 'print' para obtener el PDF."
        )
        print(json.dumps({"ok": False, "blocked": True, "reason": "already_accepted",
                          "l10n_cl_dte_status": dte_status,
                          "picking_id": picking_id, "error": msg}) if json_out else msg)
        sys.exit(2)
    execute_kw(object_, db, uid, password, "stock.picking", "create_delivery_guide", [[picking_id]])
    print(json.dumps({"ok": True, "picking_id": picking_id, "action": "create_delivery_guide"}) if json_out else "Guia de despacho creada correctamente.")


def run_send(db, uid, password, object_, picking_id, json_out):
    execute_kw(object_, db, uid, password, "stock.picking", "l10n_cl_send_dte_to_sii", [[picking_id]], {"retry_send": True})
    print(json.dumps({"ok": True, "picking_id": picking_id, "action": "l10n_cl_send_dte_to_sii"}) if json_out else "DTE enviado al SII correctamente.")


def run_verify(db, uid, password, object_, picking_id, json_out, send_to_partner):
    execute_kw(object_, db, uid, password, "stock.picking", "l10n_cl_verify_dte_status", [[picking_id]], {"send_dte_to_partner": send_to_partner})
    print(json.dumps({"ok": True, "picking_id": picking_id, "action": "l10n_cl_verify_dte_status"}) if json_out else "Estado en SII consultado y actualizado.")


def run_print(db, uid, password, object_, picking_id, json_out):
    execute_kw(object_, db, uid, password, "stock.picking", "print_delivery_guide_pdf", [[picking_id]])
    print(json.dumps({"ok": True, "picking_id": picking_id, "action": "print_delivery_guide_pdf"}) if json_out else "Solicitud de impresion de la guia enviada.")


def run_status(db, uid, password, object_, picking_id, json_out):
    rows = execute_kw(object_, db, uid, password, "stock.picking", "read", [[picking_id]], {"fields": ["name", "state", "l10n_latam_document_number", "l10n_cl_dte_status", "l10n_cl_dte_partner_status"]})
    if not rows:
        raise SystemExit("Error: picking no encontrado")
    r = rows[0]
    if json_out:
        print(json.dumps(r))
    else:
        print(f"Picking: {r.get('name')} | Estado: {r.get('state')} | Folio: {r.get('l10n_latam_document_number') or '-'} | Estado SII: {r.get('l10n_cl_dte_status') or '-'} | Envio partner: {r.get('l10n_cl_dte_partner_status') or '-'}")


def main():
    parser = argparse.ArgumentParser(description="GDE: crear guia, enviar a SII, verificar estado, imprimir")
    parser.add_argument("operation", choices=["create", "send", "verify", "print", "status"])
    parser.add_argument("--picking", required=True)
    parser.add_argument("--send-to-partner", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.operation in {"create", "send", "verify", "print"} and not args.yes:
        print("Refused: add --yes to confirm state-changing GDE operation.")
        return 1

    db, uid, password, object_ = get_connection()
    picking_id = resolve_picking(db, uid, password, object_, args.picking)

    try:
        if args.operation == "create":
            run_create(db, uid, password, object_, picking_id, args.json)
        elif args.operation == "send":
            run_send(db, uid, password, object_, picking_id, args.json)
        elif args.operation == "verify":
            run_verify(db, uid, password, object_, picking_id, args.json, args.send_to_partner)
        elif args.operation == "print":
            run_print(db, uid, password, object_, picking_id, args.json)
        elif args.operation == "status":
            run_status(db, uid, password, object_, picking_id, args.json)
    except xmlrpc.client.Fault as e:
        msg = e.faultString or str(e)
        print(json.dumps({"ok": False, "error": msg}) if args.json else f"Error Odoo: {msg}")
        sys.exit(1)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
