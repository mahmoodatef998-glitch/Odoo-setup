from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Spec v0.8.1: the open Job Orders still held reservations made in the factory before engines
    had serials (MO012 could not be finished: "Lot/Serial number is mandatory"). They are made
    again from what Pick Components really brought: the engine by its serial, nothing when the
    parts are not delivered yet."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    jobs = env["mrp.production"].search([("x4u_is_job_order", "=", True), ("state", "not in", ("done", "cancel"))])
    jobs._x4u_reserve_delivered_parts(all_parts=True)
