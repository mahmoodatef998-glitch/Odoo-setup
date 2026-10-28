from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .x4u_sale_proforma import POSTED_PAYMENT_STATES


class SaleOrder(models.Model):
    _inherit = "sale.order"

    x4u_proforma_ids = fields.One2many("x4u.sale.proforma", "order_id", string="Proformas")
    x4u_proforma_count = fields.Integer(compute="_compute_x4u_proforma_count")
    x4u_advance_payment_ids = fields.One2many(
        "account.payment", "x4u_sale_order_id", string="Advance Payments",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    x4u_advance_count = fields.Integer(compute="_compute_x4u_payments")
    x4u_amount_advance = fields.Monetary(string="Advances Received", compute="_compute_x4u_payments")
    x4u_amount_remaining = fields.Monetary(string="Remaining", compute="_compute_x4u_payments")
    x4u_final_invoice_paid = fields.Boolean(string="Final Invoice Paid", compute="_compute_x4u_payments")
    x4u_pay_before_delivery = fields.Boolean(related="payment_term_id.x4u_pay_before_delivery")

    @api.depends("x4u_proforma_ids")
    def _compute_x4u_proforma_count(self):
        for order in self:
            order.x4u_proforma_count = len(order.x4u_proforma_ids)

    @api.depends(
        "amount_total",
        "invoice_ids.state",
        "invoice_ids.amount_residual",
        "x4u_advance_payment_ids.state",
        "x4u_advance_payment_ids.amount",
        "x4u_advance_payment_ids.move_id.line_ids.amount_residual",
    )
    def _compute_x4u_payments(self):
        """B5: what came in for the order; the Salesperson sees the amounts, not the payments."""
        for order in self:
            sudo_order = order.sudo()
            currency = order.currency_id
            payments = sudo_order.x4u_advance_payment_ids.filtered(lambda p: p.state in POSTED_PAYMENT_STATES)
            invoices = sudo_order.invoice_ids.filtered(lambda m: m.state == "posted" and m.move_type == "out_invoice")
            # An applied advance shows on the invoice it paid, so only its open part counts here.
            unapplied = sum(payment._x4u_unapplied_in(currency) for payment in payments)
            paid_on_invoices = sum(invoice.amount_total - invoice.amount_residual for invoice in invoices)
            order.x4u_advance_count = len(sudo_order.x4u_advance_payment_ids)
            order.x4u_amount_advance = sum(payment._x4u_amount_in(currency) for payment in payments)
            order.x4u_amount_remaining = max(currency.round(order.amount_total - unapplied - paid_on_invoices), 0.0)
            finals = invoices.filtered(lambda m: m._x4u_is_final_invoice() and m.payment_state != "reversed")
            order.x4u_final_invoice_paid = (
                bool(finals)
                and all(invoice.payment_state in ("in_payment", "paid") for invoice in finals)
                and currency.is_zero(order.x4u_amount_remaining)
            )

    @api.model
    def _x4u_accountant_user(self):
        """Who gets the payment to-dos (Settings › Sales › Invoicing)."""
        user_id = int(self.env["ir.config_parameter"].sudo().get_param("x4u_sale.accountant_user_id") or 0)
        return self.env["res.users"].browse(user_id).exists()

    def _x4u_notify_accountant(self, summary):
        user = self._x4u_accountant_user()
        if user:
            for order in self:
                order.sudo().activity_schedule("mail.mail_activity_data_todo", user_id=user.id, summary=summary)

    def _x4u_advance_amounts(self, ratio):
        """Untaxed amount and VAT of an advance of `ratio` of the order."""
        self.ensure_one()
        currency = self.currency_id
        return currency.round(self.amount_untaxed * ratio), currency.round(self.amount_tax * ratio)

    def _x4u_next_advance_percent(self):
        """B1: the next line of the payment terms; the last line is the final invoice."""
        self.ensure_one()
        lines = self.payment_term_id.line_ids.filtered(lambda line: line.value == "percent")
        advances = lines[:-1] if len(lines) > 1 else lines.filtered(lambda line: not line.nb_days)
        issued = len(self.x4u_proforma_ids.filtered(lambda p: p.state != "cancel"))
        return advances[issued].value_amount if issued < len(advances) else 0.0

    def action_x4u_proforma(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Issue a Proforma"),
            "res_model": "x4u.sale.proforma.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_order_id": self.id, "default_percent": self._x4u_next_advance_percent()},
        }

    def action_x4u_view_proformas(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("x4u_sale.x4u_sale_proforma_action")
        action.update(domain=[("order_id", "=", self.id)], context={"create": False})
        return action

    def action_x4u_view_advances(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("account.action_account_payments")
        action.update(domain=[("x4u_sale_order_id", "=", self.id)], context={"create": False})
        return action


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    def create_invoices(self):
        """Invoices are made by Accounting (spec §7)."""
        if not self.env.su and not self.env.user.has_group("account.group_account_invoice"):
            raise AccessError(_("Invoices are made by the Accountant."))
        return super().create_invoices()
