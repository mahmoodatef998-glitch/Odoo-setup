"""Spec §20 on an existing install (UAT 2026-11-24): the stock categories at the average cost (the
stock keeps its value), the cost of sales at the delivery (what is left in GDNI goes to the cost of
sales), the serials on the delivery slip."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import x4u_setup


def migrate(cr, version):
    x4u_setup(api.Environment(cr, SUPERUSER_ID, {}))
