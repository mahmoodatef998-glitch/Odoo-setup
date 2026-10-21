"""Two pricelists only (Standard AED, Export USD) and 5% Sharjah as default sales tax (2026-10-21)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_setup_4u.hooks import remove_default_pricelist, use_sharjah_sales_tax


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    remove_default_pricelist(env)
    use_sharjah_sales_tax(env)
