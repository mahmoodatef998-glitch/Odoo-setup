"""UAT Phase 2.2 on an existing install: receipts from vendors need their Delivery Note."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["res.company"].search([]).write({"x4u_receipt_dn_required": True})
