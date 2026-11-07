"""v1.4 on an existing install: landed costs and their clearing accounts (spec §10)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import x4u_setup


def migrate(cr, version):
    x4u_setup(api.Environment(cr, SUPERUSER_ID, {}))
