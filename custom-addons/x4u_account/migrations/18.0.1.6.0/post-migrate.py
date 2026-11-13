"""v1.6 on an existing install: PDC Received (customer cheques), fiscal years, monthly soft lock, MIS reports (spec §12-§14)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import x4u_setup


def migrate(cr, version):
    x4u_setup(api.Environment(cr, SUPERUSER_ID, {}))
