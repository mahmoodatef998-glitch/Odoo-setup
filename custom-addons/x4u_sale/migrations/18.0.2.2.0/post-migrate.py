from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Spec v0.7 O6: a PI for each payment. An order's one PI (v0.5) becomes the PI of its first
    payment, the other payments get theirs; a PI without a payment was a request: cancelled. The
    LPO to-dos of v0.6 are closed."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Payment = env["account.payment"]
    Proforma = env["x4u.sale.proforma"]
    for proforma in Proforma.search([("cancelled", "=", False), ("payment_id", "=", False)], order="id"):
        payments = Payment.search(
            [("x4u_proforma_id", "=", proforma.id), ("state", "in", ("in_process", "paid"))], order="date, id"
        )
        if not payments:
            proforma.cancelled = True
            continue
        order = proforma.order_id
        first = payments[0]
        proforma.write(
            {
                "payment_id": first.id,
                "date": first.date,
                "sequence": 1,
                "name": "%s-PI1" % order.name,
                "amount_payment": first._x4u_amount_in(order.currency_id),
            }
        )
        (payments - first).write({"x4u_proforma_id": False})
        Proforma._x4u_for_payments(payments - first)
    lpo = env.ref("x4u_sale.mail_activity_type_lpo", raise_if_not_found=False)
    if lpo:
        env["mail.activity"].search([("activity_type_id", "=", lpo.id)]).unlink()
    old_template = env.ref("x4u_sale.mail_template_proforma_v2", raise_if_not_found=False)
    if old_template:
        old_template.unlink()
    env.add_to_compute(Proforma._fields["amount_paid"], Proforma.search([]))
    env.add_to_compute(Proforma._fields["amount_remaining"], Proforma.search([]))
    env.add_to_compute(Proforma._fields["state"], Proforma.search([]))
