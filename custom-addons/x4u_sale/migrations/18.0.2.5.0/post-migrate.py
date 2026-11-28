"""Spec v0.9 on an existing database: a quotation that already has its PI, or went to the
Accountant, was accepted by the customer - it is Accepted (and locked) from now on."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env["sale.order"].with_context(active_test=False).search(
        [
            ("state", "in", ("draft", "sent")),
            ("x4u_accepted_date", "=", False),
            "|",
            ("x4u_po_check", "!=", False),
            ("x4u_proforma_ids.state", "in", ("issued", "partial", "paid")),
        ]
    )
    for order in orders:
        order.write({"x4u_accepted_date": order.write_date, "x4u_accepted_user_id": order.user_id.id or SUPERUSER_ID})
