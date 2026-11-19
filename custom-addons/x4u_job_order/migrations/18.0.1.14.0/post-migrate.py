from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Spec v0.14 H4: the figures of Order Profitability for the Job Orders already there."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["x4u.job.order"].search([])._x4u_refresh_profitability()
