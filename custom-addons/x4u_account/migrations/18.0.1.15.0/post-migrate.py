"""The accounting team, 2026-11-27, on an existing install: 530061 PENALTY becomes the administrative
penalty (530088 PENALTY - OPERATING is made by the setup), every Focus expense account gets its
P&L group (O / S / G / X) and the 4U Management P&L shows them."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import x4u_setup


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env["res.company"].search([]):
        Account = env["account.account"].with_company(company)
        penalty = Account.search([*Account._check_company_domain(company), ("code", "=", "530061")], limit=1)
        if penalty and penalty.with_context(lang="en_US").name == "PENALTY":
            penalty.with_context(lang="en_US").name = "PENALTY - ADMINISTRATIVE"
    x4u_setup(env)
