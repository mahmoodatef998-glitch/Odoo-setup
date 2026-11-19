"""Spec §17 on an existing install: the Monthly P&L of this year."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import _monthly_pl


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env["res.company"].search([("chart_template", "!=", False)]):
        _monthly_pl(env, company)
