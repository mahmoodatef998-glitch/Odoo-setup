"""Pricelists without the currency in the name, owned by the company, no extra Default.

The records are noupdate, so databases installed with 18.0.1.0.0 get the change here.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_setup_4u.hooks import PRICELISTS, remove_default_pricelist


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    company = env.ref("base.main_company")
    for xmlid, name in PRICELISTS.items():
        pricelist = env.ref("x4u_setup_4u." + xmlid, raise_if_not_found=False)
        if pricelist:
            pricelist.with_context(lang="en_US").write({"name": name, "company_id": company.id})
    remove_default_pricelist(env)
