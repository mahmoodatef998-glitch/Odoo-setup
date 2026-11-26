"""The user, 2026-11-26 (fewer steps): on an existing install the vendor bill is drafted at the receipt."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["res.company"].search([]).write({"x4u_receipt_draft_bill": True})
