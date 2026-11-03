from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_amount

from odoo.addons.x4u_sale.models.x4u_sale_proforma import POSTED_PAYMENT_STATES


class AccountPayment(models.Model):
    _inherit = "account.payment"

    x4u_purchase_order_id = fields.Many2one(
        "purchase.order",
        string="Purchase Order",
        index="btree_not_null",
        copy=False,
        tracking=True,
        domain="[('state', 'in', ('purchase', 'done')), ('partner_id.commercial_partner_id', '=', x4u_commercial_partner_id)]",
        help="An advance for this PO: the vendor bill of the PO applies it by itself.",
    )
    x4u_purchase_proforma_id = fields.Many2one(
        "x4u.purchase.proforma",
        string="Vendor PI",
        index="btree_not_null",
        copy=False,
        tracking=True,
        domain="[('order_id', '=', x4u_purchase_order_id), ('state', '=', 'open')]",
    )

    @api.onchange("x4u_purchase_proforma_id")
    def _onchange_x4u_purchase_proforma_id(self):
        proforma = self.x4u_purchase_proforma_id
        if proforma:
            self.x4u_purchase_order_id = proforma.order_id
            self.amount = proforma.amount_due_now
            self.memo = self.memo or proforma.name

    @api.constrains("x4u_purchase_order_id", "x4u_purchase_proforma_id", "partner_id", "payment_type", "partner_type")
    def _check_x4u_purchase_order(self):
        for payment in self:
            order = payment.x4u_purchase_order_id
            proforma = payment.x4u_purchase_proforma_id
            if proforma and proforma.order_id != order:
                raise ValidationError(_("Vendor PI %s belongs to another purchase order.", proforma.name))
            if order and (
                payment.payment_type != "outbound"
                or payment.partner_type != "supplier"
                or payment.partner_id.commercial_partner_id != order.partner_id.commercial_partner_id
            ):
                raise ValidationError(_("Only money paid to the vendor of %s can be an advance for it.", order.name))

    def action_post(self):
        res = super().action_post()
        # The vendor PI suggests the next payment of the schedule again.
        self.x4u_purchase_proforma_id.sudo().amount_due_manual = 0.0
        self._x4u_log_on_purchase_order(_("Payment sent"))
        return res

    def action_cancel(self):
        self._x4u_log_on_purchase_order(_("Payment cancelled"))
        return super().action_cancel()

    def _x4u_log_on_purchase_order(self, label):
        for payment in self.filtered("x4u_purchase_order_id"):
            payment.x4u_purchase_order_id.sudo().message_post(
                body=_(
                    "%(label)s: %(amount)s (%(ref)s)",
                    label=label,
                    amount=format_amount(self.env, payment.amount, payment.currency_id),
                    ref=payment.x4u_purchase_proforma_id.name or payment.name,
                )
            )


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        posted = super()._post(soft)
        posted.filtered(lambda move: move.move_type == "in_invoice")._x4u_apply_vendor_advances()
        return posted

    def _x4u_apply_vendor_advances(self):
        """P8: the bill of a PO applies the advances paid for it."""
        Payment = self.env["account.payment"].sudo()
        for bill in self:
            orders = bill.invoice_line_ids.purchase_line_id.order_id
            if not orders:
                continue
            payments = Payment.search(
                [("x4u_purchase_order_id", "in", orders.ids), ("state", "in", POSTED_PAYMENT_STATES)], order="date, id"
            )
            bill._x4u_assign_payments(payments, lambda payment: payment.x4u_purchase_proforma_id.name)
