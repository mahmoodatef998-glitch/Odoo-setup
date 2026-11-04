from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """v0.6: the LPO comes after the Confirm. Confirmed orders without it wait for it, instead of
    waiting for the Accountant's check (no to-dos for the old ones)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env["sale.order"].search([("state", "=", "sale"), ("x4u_po_check", "=", "to_check")])
    orders.filtered(lambda order: not order._x4u_has_lpo()).write({"x4u_po_check": "waiting"})
