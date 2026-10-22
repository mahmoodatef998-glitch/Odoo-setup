"""Approval to-do for purchase orders already waiting for the General Manager (guide R2, 2026-10-22)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["purchase.order"].search([("state", "=", "to approve")])._x4u_ask_approval()
