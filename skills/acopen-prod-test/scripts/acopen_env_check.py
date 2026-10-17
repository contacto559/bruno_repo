#!/usr/bin/env python3
"""
Muestra el entorno Acopen activo (URL y DB) según ODOO_ACOPEN_USE_TEST.
Solo lee variables de entorno; no imprime usuario ni contraseña.
"""
import os

USE_TEST_VALUES = ("1", "true", "yes")


def main():
    use_test = (os.environ.get("ODOO_ACOPEN_USE_TEST") or "").strip().lower()
    if use_test in USE_TEST_VALUES:
        url = os.environ.get("ODOO_ACOPEN_TEST_URL", "(no definido)")
        db = os.environ.get("ODOO_ACOPEN_TEST_DB", "(no definido)")
        print(f"Acopen pruebas — URL: {url}, DB: {db}")
    else:
        url = os.environ.get("ODOO_URL", "(no definido)")
        db = os.environ.get("ODOO_DB", "(no definido)")
        print(f"Acopen producción — URL: {url}, DB: {db}")


if __name__ == "__main__":
    main()
