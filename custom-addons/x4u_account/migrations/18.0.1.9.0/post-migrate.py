"""Spec §18 on an existing install: the daily GBP rate provider."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import _gbp_rate_provider


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env["res.company"].search([("chart_template", "!=", False)]):
        _gbp_rate_provider(env, company)
