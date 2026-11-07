"""v1.1 on an existing install: equity accounts, Petty Cash, statements, automatic reconciliation (spec §2-§5)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import x4u_setup


def migrate(cr, version):
    x4u_setup(api.Environment(cr, SUPERUSER_ID, {}))
