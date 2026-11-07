"""v1.3 on an existing install: perpetual inventory + Anglo-Saxon, the fixed assets group types (spec §9)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_account.hooks import x4u_setup


def migrate(cr, version):
    x4u_setup(api.Environment(cr, SUPERUSER_ID, {}))
