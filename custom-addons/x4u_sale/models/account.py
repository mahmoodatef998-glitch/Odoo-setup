from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_amount

from .x4u_sale_proforma import POSTED_PAYMENT_STATES


class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"

    x4u_pay_before_delivery = fields.Boolean(
        string="Paid Before Delivery",
        help="The first payment comes with the order and the last one before delivery (on the PI). The Accountant "
        "gets a to-do when the generator is ready; a delivery before the tax invoice is paid is written on the order.",
    )
    x4u_custom = fields.Boolean(
        string="Custom Schedule",
        help="The salesperson or the buyer writes the payment schedule on the order (percentages and when).",
    )


class AccountPayment(models.Model):
    _inherit = "account.payment"

    x4u_commercial_partner_id = fields.Many2one(related="partner_id.commercial_partner_id")
    x4u_sale_order_id = fields.Many2one(
        "sale.order",
        string="Sales Order",
        index="btree_not_null",
        copy=False,
        tracking=True,
        domain="[('state', '=', 'sale'), ('partner_id.commercial_partner_id', '=', x4u_commercial_partner_id)]",
        help="An advance for this order: the final invoice of the order applies it by itself.",
    )
    x4u_proforma_id = fields.Many2one(
        "x4u.sale.proforma",
        string="PI",
        index="btree_not_null",
        copy=False,
        tracking=True,
        domain="[('order_id', '=', x4u_sale_order_id), ('state', '=', 'open')]",
    )

    @api.onchange("x4u_proforma_id")
    def _onchange_x4u_proforma_id(self):
        proforma = self.x4u_proforma_id
        if proforma:
            self.x4u_sale_order_id = proforma.order_id
            self.amount = proforma.amount_due_now
            self.memo = self.memo or proforma.name

    @api.constrains("x4u_sale_order_id", "x4u_proforma_id", "partner_id", "payment_type", "partner_type")
    def _check_x4u_sale_order(self):
        for payment in self:
            order = payment.x4u_sale_order_id
            proforma = payment.x4u_proforma_id
            if proforma and proforma.order_id != order:
                raise ValidationError(_("PI %s belongs to another sales order.", proforma.name))
            if order and (
                payment.payment_type != "inbound"
                or payment.partner_type != "customer"
                or payment.partner_id.commercial_partner_id != order.partner_id.commercial_partner_id
            ):
                raise ValidationError(_("Only money received from the customer of %s can be an advance for it.", order.name))

    def write(self, vals):
        proformas = self.x4u_proforma_id
        res = super().write(vals)
        if {"state", "amount", "currency_id", "x4u_proforma_id"} & set(vals):
            (proformas | self.x4u_proforma_id)._x4u_sync_followup()
        return res

    def action_post(self):
        res = super().action_post()
        # The PI asks for the next payment of the schedule again.
        proformas = self.x4u_proforma_id.sudo()
        proformas.amount_due_manual = 0.0
        proformas._x4u_sync_followup()
        self._x4u_log_on_order(_("Payment received"))
        return res

    def action_cancel(self):
        self._x4u_log_on_order(_("Payment cancelled"))
        return super().action_cancel()

    def _x4u_log_on_order(self, label):
        for payment in self.filtered("x4u_sale_order_id"):
            payment.x4u_sale_order_id.sudo().message_post(
                body=_(
                    "%(label)s: %(amount)s (%(ref)s)",
                    label=label,
                    amount=format_amount(self.env, payment.amount, payment.currency_id),
                    ref=payment.x4u_proforma_id.name or payment.name,
                )
            )

    def _x4u_amount_in(self, currency):
        self.ensure_one()
        return self.currency_id._convert(self.amount, currency, self.company_id, self.date)

    def _x4u_open_counterpart_lines(self):
        """The customer (or vendor) line of the payment that no invoice took yet."""
        self.ensure_one()
        if not self.move_id:
            return self.env["account.move.line"]
        _liquidity, counterpart, _writeoff = self._seek_for_lines()
        return counterpart.filtered(
            lambda line: line.account_id.account_type in ("asset_receivable", "liability_payable") and not line.reconciled
        )

    def _x4u_unapplied_in(self, currency):
        """What the tax invoice (or the bill) can still apply (S8)."""
        self.ensure_one()
        if not self.move_id:
            return self._x4u_amount_in(currency)
        # Credit on the customer's side for money in, debit on the vendor's side for money out.
        amount = abs(sum(self._x4u_open_counterpart_lines().mapped("amount_residual_currency")))
        return self.currency_id._convert(amount, currency, self.company_id, self.date)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        posted = super()._post(soft)
        posted.filtered(lambda move: move.move_type == "out_invoice")._x4u_apply_advances()
        return posted

    def _x4u_is_final_invoice(self):
        """A regular invoice of a sale, not a down payment invoice."""
        self.ensure_one()
        return any(not line.is_downpayment for line in self.invoice_line_ids.sale_line_ids)

    def _x4u_apply_advances(self):
        """S8: the payments of the order, as if the Accountant clicked Add on each outstanding credit."""
        Payment = self.env["account.payment"].sudo()
        for invoice in self.filtered(lambda move: move._x4u_is_final_invoice()):
            orders = invoice.invoice_line_ids.sale_line_ids.order_id
            payments = Payment.search(
                [("x4u_sale_order_id", "in", orders.ids), ("state", "in", POSTED_PAYMENT_STATES)], order="date, id"
            )
            invoice._x4u_assign_payments(payments, lambda payment: payment.x4u_proforma_id.name)

    def _x4u_assign_payments(self, payments, reference):
        """Apply the open part of each payment of the same partner, then say which on the chatter."""
        self.ensure_one()
        counterpart = self.line_ids.filtered(lambda line: line.display_type == "payment_term").account_id
        applied = []
        for payment in payments:
            if self.currency_id.is_zero(self.amount_residual):
                break
            if payment.partner_id.commercial_partner_id != self.commercial_partner_id:
                continue
            lines = payment._x4u_open_counterpart_lines().filtered(lambda line: line.account_id in counterpart)
            if not lines:
                continue
            before = self.amount_residual
            for line in lines:
                self.sudo().js_assign_outstanding_line(line.id)
            applied.append(
                "%s %s"
                % (
                    reference(payment) or payment.name,
                    format_amount(self.env, before - self.amount_residual, self.currency_id),
                )
            )
        if applied:
            self.message_post(body=_("Advances applied: %s", ", ".join(applied)))
