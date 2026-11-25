"""On an existing install: the Generator Supply template gets 4U's terms (QT 1112), unless changed by hand."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_setup_4u.hooks import set_quotation_terms


def migrate(cr, version):
    set_quotation_terms(api.Environment(cr, SUPERUSER_ID, {}))
