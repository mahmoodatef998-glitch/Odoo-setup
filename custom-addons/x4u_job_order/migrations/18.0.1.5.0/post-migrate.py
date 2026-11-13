"""Spec v0.5 (2026-11-07): an analytic account per Job Order, also for the Job Orders that exist
already, carried to their sales lines, invoice lines and cost of sales."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_job_order.hooks import setup_job_analytic


def migrate(cr, version):
    setup_job_analytic(api.Environment(cr, SUPERUSER_ID, {}))
