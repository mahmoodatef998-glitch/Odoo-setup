"""The accounting team, 2026-11-27, on an existing install: 216001 Advances from Customers and 137012
Advances to Suppliers (made by the setup), and payments straight to the bank: the payment methods
post to the bank (cash) account and what is still on Outstanding Receipts / Payments moves there."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import x4u_direct_bank, x4u_setup


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    x4u_setup(env)
    x4u_direct_bank(env)
