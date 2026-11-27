"""The accounting team, 2026-11-27: the expense accounts the Accountant added in ATA (petrol and
telephone per person, accounting fee, depreciation) get their P&L group (G)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import _pl_groups


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env["res.company"].search([]):
        company_env = env(context=dict(env.context, allowed_company_ids=company.ids))
        _pl_groups(company_env, company.with_env(company_env))
