"""The user, 2026-11-27: a draft vendor bill whose 4U number was typed by hand gives that number to
its Vendor Invoice No. and takes its own 4U number at Confirm."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    api.Environment(cr, SUPERUSER_ID, {})["account.move"]._x4u_clear_typed_bill_numbers()
