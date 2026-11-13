"""Spec v0.6 R4 (2026-11-10): close the material request lines of Job Order parts that already
got their stock, so Purchasing does not buy them twice."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    jobs = env["mrp.production"].search([("x4u_is_job_order", "=", True)])
    jobs._x4u_component_moves()._x4u_close_covered_requests()
