"""x4u_generator_datasheet §9 on an existing install: the quotation sent by email is the 4U one."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_job_order.hooks import use_4u_quotation_report


def migrate(cr, version):
    use_4u_quotation_report(api.Environment(cr, SUPERUSER_ID, {}))
