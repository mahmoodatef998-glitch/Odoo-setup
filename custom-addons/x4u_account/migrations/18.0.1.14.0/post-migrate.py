"""The accounting team, 2026-11-27: on an existing install, the Aged Partner Balance opens in
0-30 / 31-60 / 61-90 / +90 days, aged from the invoice date."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import _aging_config


def migrate(cr, version):
    _aging_config(api.Environment(cr, SUPERUSER_ID, {}))
