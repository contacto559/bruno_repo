#!/usr/bin/env python3
"""
Purchase receipts (incoming pickings) via Odoo XML-RPC.
Lists receipts for a PO, searches by origin or folio, and can validate receipts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import xmlrpc.client

sys.path.append(str(Path(__file__).resolve().parents[2]))
from shared.acopen_rpc import execute_kw as kw
from shared.acopen_rpc import get_connection


def cmd_list_purchase(object_, db, uid, password, po_name, json_out):
    po_ids = kw(object_, db, uid, password, "purchase.order", "search", [[["name", "=", po_name]]], {"limit": 5})
    if not po_ids:
        msg = f"No purchase order found with name '{po_name}'"
        print(json.dumps({"ok": False, "error": msg}) if json_out else msg)
        return 1
    domain = [["purchase_id", "in", po_ids]]
    pick_ids = kw(object_, db, uid, password, "stock.picking", "search", [domain], {"order": "id desc", "limit": 50})
    if not pick_ids:
        msg = f"No incoming receipts linked to PO '{po_name}'"
        print(json.dumps({"ok": True, "purchase_order": po_name, "pickings": [], "note": msg}) if json_out else msg)
        return 0
    fields = ["name", "state", "scheduled_date", "partner_id", "origin", "purchase_id"]
    rows = kw(object_, db, uid, password, "stock.picking", "read", [pick_ids], {"fields": fields})
    if json_out:
        print(json.dumps({"ok": True, "purchase_order": po_name, "pickings": rows}))
    else:
        print(f"Incoming receipts for PO {po_name}:")
        for r in rows:
            print(f"  {r['name']} | state={r['state']} | scheduled={r.get('scheduled_date')}")
    return 0


def cmd_find_folio(object_, db, uid, password, folio, json_out):
    pick_ids = kw(object_, db, uid, password, "stock.picking", "search", [[["l10n_latam_document_number", "=", folio]]], {"limit": 20})
    if not pick_ids:
        print(json.dumps({"ok": True, "pickings": [], "note": "No pickings with this folio."}) if json_out else "No pickings found with that guide folio.")
        return 0
    rows = kw(object_, db, uid, password, "stock.picking", "read", [pick_ids], {"fields": ["name", "state", "purchase_id", "partner_id", "origin", "l10n_latam_document_number"]})
    if json_out:
        print(json.dumps({"ok": True, "pickings": rows}))
    else:
        for r in rows:
            print(f"{r['name']} | state={r['state']} | origin={r.get('origin')}")
    return 0


def cmd_search_incoming(object_, db, uid, password, origin_sub, json_out):
    domain = [["picking_type_id.code", "=", "incoming"], ["origin", "ilike", origin_sub]]
    pick_ids = kw(object_, db, uid, password, "stock.picking", "search", [domain], {"order": "id desc", "limit": 30})
    rows = kw(object_, db, uid, password, "stock.picking", "read", [pick_ids], {"fields": ["name", "state", "origin", "purchase_id", "partner_id", "scheduled_date"]})
    if json_out:
        print(json.dumps({"ok": True, "pickings": rows}))
    else:
        print(f"Incoming pickings with origin containing '{origin_sub}':")
        for r in rows:
            print(f"  {r['name']} | {r['state']} | {r.get('origin')}")
    return 0


def cmd_search_bill(object_, db, uid, password, text, json_out):
    domain = [["move_type", "=", "in_invoice"], "|", "|", ["ref", "ilike", text], ["narration", "ilike", text], ["payment_reference", "ilike", text]]
    move_ids = kw(object_, db, uid, password, "account.move", "search", [domain], {"order": "id desc", "limit": 20})
    rows = kw(object_, db, uid, password, "account.move", "read", [move_ids], {"fields": ["name", "state", "ref", "partner_id", "invoice_date", "amount_total"]})
    if json_out:
        print(json.dumps({"ok": True, "vendor_bills": rows}))
    else:
        print(f"Vendor bills matching '{text}':")
        for r in rows:
            print(f"  {r['name']} | {r['state']} | ref={r.get('ref')} | total={r.get('amount_total')}")
    return 0


def cmd_validate(object_, db, uid, password, picking_ref, json_out):
    try:
        pid = int(picking_ref)
        ids = kw(object_, db, uid, password, "stock.picking", "search", [[["id", "=", pid]]], {"limit": 1})
    except ValueError:
        ids = kw(object_, db, uid, password, "stock.picking", "search", [[["name", "=", picking_ref]]], {"limit": 1})
    if not ids:
        raise SystemExit(f"Picking not found: {picking_ref}")
    pid = ids[0]
    kw(object_, db, uid, password, "stock.picking", "button_validate", [[pid]])
    print(json.dumps({"ok": True, "picking_id": pid, "validated": True}) if json_out else f"Receipt validated: picking id {pid}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Purchase receipts helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("list-purchase")
    p1.add_argument("--po", required=True)
    p1.add_argument("--json", action="store_true")

    p2 = sub.add_parser("find-folio")
    p2.add_argument("--folio", required=True)
    p2.add_argument("--json", action="store_true")

    p3 = sub.add_parser("search-incoming")
    p3.add_argument("--origin", required=True)
    p3.add_argument("--json", action="store_true")

    p4 = sub.add_parser("search-bill")
    p4.add_argument("--text", required=True)
    p4.add_argument("--json", action="store_true")

    p5 = sub.add_parser("validate")
    p5.add_argument("--picking", required=True)
    p5.add_argument("--yes", action="store_true")
    p5.add_argument("--json", action="store_true")

    args = parser.parse_args()
    db, uid, password, object_ = get_connection()

    if args.cmd == "validate" and not args.yes:
        print("Refused: add --yes to confirm receipt validation.")
        return 1

    try:
        if args.cmd == "list-purchase":
            return cmd_list_purchase(object_, db, uid, password, args.po, args.json)
        if args.cmd == "find-folio":
            return cmd_find_folio(object_, db, uid, password, args.folio, args.json)
        if args.cmd == "search-incoming":
            return cmd_search_incoming(object_, db, uid, password, args.origin, args.json)
        if args.cmd == "search-bill":
            return cmd_search_bill(object_, db, uid, password, args.text, args.json)
        if args.cmd == "validate":
            return cmd_validate(object_, db, uid, password, args.picking, args.json)
    except xmlrpc.client.Fault as e:
        err = e.faultString or str(e)
        print(json.dumps({"ok": False, "error": err}) if args.json else f"Odoo error: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
