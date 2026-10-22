"""4U document prefix: customer invoices 4U-INV-2026-0001, credit notes 4U-CN-2026-0001 (2026-10-22)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_setup_4u.hooks import DOCUMENT_PREFIX


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    company = env.ref("base.main_company")
    if not company.x4u_document_prefix:
        company.x4u_document_prefix = DOCUMENT_PREFIX
