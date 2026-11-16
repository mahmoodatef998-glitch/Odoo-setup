"""Spec v0.9 C1: the CKD category is costed FIFO like the other parts (its accounts come from
x4u_account). The open Job Orders keep their engine + alternator + body."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_job_order.hooks import set_costing


def migrate(cr, version):
    set_costing(api.Environment(cr, SUPERUSER_ID, {}))
