from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount

# A confirmed payment counts: In Process until the bank statement matches it, then Paid.
POSTED_PAYMENT_STATES = ("in_process", "paid")
PROFORMA_STATES = [
    ("issued", "Issued"),
    ("invoiced", "Invoiced"),
    ("cancel", "Cancelled"),
]


class X4uSaleProforma(models.Model):
    """A PI for each payment, made after the money came in (spec v0.7 O6): what this payment was,
    what was paid up to it, and what is left of the order.

    Not a tax invoice, no journal entry: the payment is linked to the sales order, and the one tax
    invoice of the whole order applies the payments at the end (O8).
    """

    _name = "x4u.sale.proforma"
    _description = "Proforma Invoice"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Number", required=True, readonly=True, copy=False)
    sequence = fields.Integer(readonly=True, copy=False)
    order_id = fields.Many2one(
        "sale.order", string="Sales Order", required=True, readonly=True, index=True, ondelete="restrict",
        check_company=True,
    )
    payment_id = fields.Many2one(
        "account.payment", string="Payment", readonly=True, index="btree_not_null", copy=False,
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    partner_id = fields.Many2one(related="order_id.partner_id", string="Customer", store=True, index=True)
    user_id = fields.Many2one(related="order_id.user_id", string="Salesperson", store=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="order_id.currency_id", store=True)
    client_order_ref = fields.Char(related="order_id.client_order_ref", string="LPO Number")
    date = fields.Date(required=True, readonly=True, default=fields.Date.context_today)
    amount_untaxed = fields.Monetary(related="order_id.amount_untaxed")
    amount_tax = fields.Monetary(related="order_id.amount_tax", string="VAT")
    amount_total = fields.Monetary(related="order_id.amount_total", string="Order Total")
    amount_payment = fields.Monetary(string="This Payment", readonly=True)
    amount_paid = fields.Monetary(string="Paid to Date", compute="_compute_amounts", store=True)
    amount_remaining = fields.Monetary(string="Remaining", compute="_compute_amounts", store=True)
    schedule_ids = fields.One2many(related="order_id.x4u_schedule_ids", string="Payment Schedule")
    cancelled = fields.Boolean(readonly=True, copy=False)
    state = fields.Selection(PROFORMA_STATES, string="Status", compute="_compute_state", store=True, tracking=True)

    @api.depends("amount_payment", "sequence", "cancelled", "order_id.amount_total", "order_id.x4u_proforma_ids.amount_payment")
    def _compute_amounts(self):
        for proforma in self:
            earlier = proforma.order_id.sudo().x4u_proforma_ids.filtered(
                lambda p, s=proforma.sequence: not p.cancelled and p.sequence <= s
            )
            paid = sum(earlier.mapped("amount_payment"))
            proforma.amount_paid = paid
            proforma.amount_remaining = max(proforma.currency_id.round(proforma.amount_total - paid), 0.0)

    @api.depends(
        "cancelled",
        "order_id.order_line.invoice_lines.move_id.state",
        "order_id.order_line.invoice_lines.move_id.payment_state",
    )
    def _compute_state(self):
        for proforma in self:
            if proforma.cancelled:
                proforma.state = "cancel"
            elif proforma.order_id.sudo()._x4u_final_invoices():
                proforma.state = "invoiced"
            else:
                proforma.state = "issued"

    @api.model_create_multi
    def create(self, vals_list):
        """Numbered after the sales order and its payments: S012-PI1, S012-PI2..."""
        last = {}
        for vals in vals_list:
            order = self.env["sale.order"].browse(vals["order_id"])
            if order.id not in last:
                last[order.id] = max(order.sudo().x4u_proforma_ids.mapped("sequence"), default=0)
            last[order.id] += 1
            vals.update(sequence=last[order.id], name="%s-PI%s" % (order.name, last[order.id]))
        proformas = super().create(vals_list)
        for proforma in proformas:
            proforma.order_id.sudo().message_post(
                body=_(
                    "PI %(name)s: %(payment)s received, %(paid)s paid to date, %(left)s remaining.",
                    name=proforma.name,
                    payment=format_amount(self.env, proforma.amount_payment, proforma.currency_id),
                    paid=format_amount(self.env, proforma.amount_paid, proforma.currency_id),
                    left=format_amount(self.env, proforma.amount_remaining, proforma.currency_id),
                )
            )
        return proformas

    @api.model
    def _x4u_for_payments(self, payments):
        """One PI for each payment of an order that has none yet (O6)."""
        values = []
        for payment in payments.sudo().filtered(lambda p: p.x4u_sale_order_id and not p.x4u_proforma_id):
            order = payment.x4u_sale_order_id
            values.append(
                {
                    "order_id": order.id,
                    "payment_id": payment.id,
                    "date": payment.date,
                    "amount_payment": payment._x4u_amount_in(order.currency_id),
                }
            )
        proformas = self.sudo().create(values) if values else self.sudo()
        for proforma in proformas:
            proforma.payment_id.x4u_proforma_id = proforma
        return proformas

    @api.ondelete(at_uninstall=False)
    def _unlink_only_cancelled(self):
        if any(proforma.state != "cancel" for proforma in self):
            raise UserError(_("A PI goes with its payment: cancel the payment instead."))

    def _x4u_cancel(self):
        """The payment was cancelled: its PI goes with it, and the later ones count again."""
        self.write({"cancelled": True})
        for proforma in self:
            proforma.order_id.sudo().message_post(body=_("PI %s cancelled with its payment.", proforma.name))
        later = self.order_id.sudo().x4u_proforma_ids
        later.modified(["amount_payment"])

    def action_send(self):
        self.ensure_one()
        template = self.env.ref("x4u_sale.mail_template_proforma", raise_if_not_found=False)
        return {
            "type": "ir.actions.act_window",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_model": self._name,
                "default_res_ids": self.ids,
                "default_template_id": template.id if template else False,
                "default_composition_mode": "comment",
                "force_email": True,
            },
        }

    def _x4u_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def action_view_payment(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "res_id": self.payment_id.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def x4u_next_payments(self):
        """The payments of the schedule still to come, for the PDF."""
        self.ensure_one()
        return self.schedule_ids.filtered(lambda line: line.state != "paid")

    def x4u_bank_accounts(self):
        """The company's bank accounts for the PDF (spec §6 S6)."""
        self.ensure_one()
        return self.company_id.sudo().partner_id.bank_ids
