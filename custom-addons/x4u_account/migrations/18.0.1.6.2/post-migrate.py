"""x4u_job_order spec v0.9 C1: the new CKD category gets its accounts and perpetual valuation."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import x4u_setup


def migrate(cr, version):
    x4u_setup(api.Environment(cr, SUPERUSER_ID, {}))
