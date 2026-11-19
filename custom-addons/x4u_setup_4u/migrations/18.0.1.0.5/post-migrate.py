"""Installation and transport are quoted "As requested" (x4u_sale spec v0.8 A1, 2026-11-19)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_setup_4u.hooks import set_price_on_request


def migrate(cr, version):
    set_price_on_request(api.Environment(cr, SUPERUSER_ID, {}))
