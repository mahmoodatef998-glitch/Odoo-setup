"""Generator catalog, step 2 (spec x4u_generator_datasheet §6): load private/datasheets/catalog.json
(scripts/generator_catalog.py) into a database - every 4U model with its datasheet, alternators,
components, BoM and 2026 list prices. Safe to run again; changes no other product.

    docker compose run --rm -T -v "$PWD/private/datasheets:/tmp/x4u_catalog:ro" web \
        odoo shell -d <database> --no-http < scripts/import_generators.py

X4U_MODELS=4U-C300,4U-P500 limits it to those models.
"""
import json
import os

path = os.environ.get("X4U_CATALOG") or "/tmp/x4u_catalog/catalog.json"
entries = json.load(open(path, encoding="utf-8"))
wanted = {code.strip().upper() for code in (os.environ.get("X4U_MODELS") or "").split(",") if code.strip()}
if wanted:
    entries = [entry for entry in entries if entry["code"].upper() in wanted]
report = env["x4u.generator.catalog"]._x4u_import(entries)
env.cr.commit()
print("CATALOG-BEGIN")
print("models %(models)s, variants %(variants)s, with a list price %(priced_variants)s" % report)
print("price on request: %s" % len(report["price_on_request"]))
print("CATALOG-END")
