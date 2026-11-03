from odoo import SUPERUSER_ID, api

# v1 let salespeople see the proformas; the PI is now the Accountant's only (spec §6 S6).
OLD_RULES = ("x4u_sale.x4u_sale_proforma_personal_rule", "x4u_sale.x4u_sale_proforma_all_rule")


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in OLD_RULES + ("x4u_sale.mail_template_proforma_v1",):
        record = env.ref(xmlid, raise_if_not_found=False)
        if record:
            record.unlink()
    # The orders from before the schedules get the one of their terms.
    Order = env["sale.order"]
    Order.search([("x4u_schedule_ids", "=", False), ("state", "!=", "cancel")])._x4u_fill_schedule()
    # Confirmed orders wait for the Accountant's PO check like new ones (no to-dos for the old ones).
    Order.search([("state", "=", "sale"), ("x4u_po_check", "=", False)]).write({"x4u_po_check": "to_check"})
