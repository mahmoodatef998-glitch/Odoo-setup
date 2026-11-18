"""Spec §16 on an existing install: the budget of this year and the 4U P&L vs Budget."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import x4u_setup


def migrate(cr, version):
    x4u_setup(api.Environment(cr, SUPERUSER_ID, {}))
