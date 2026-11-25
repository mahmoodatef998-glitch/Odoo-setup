"""The 4U letterhead of the quotation (x4u_generator_datasheet §9): upload the two images from
private/branding/ (git-ignored, they carry the company's details) to the company.

    docker compose run --rm -T -v "$PWD/private/branding:/tmp/x4u_branding:ro" web \
        odoo shell -d <database> --no-http < scripts/set_letterhead.py
"""
import base64
import os

folder = os.environ.get("X4U_BRANDING") or "/tmp/x4u_branding"
company = env["res.company"].search([("name", "ilike", "4U Power")], limit=1) or env.company
images = {"x4u_letterhead_header": "letterhead-header.png", "x4u_letterhead_footer": "letterhead-brands.png"}
company.write({field: base64.b64encode(open(os.path.join(folder, name), "rb").read()) for field, name in images.items()})
env.cr.commit()
print("LETTERHEAD set on", company.name)
