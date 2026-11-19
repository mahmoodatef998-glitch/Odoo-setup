from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount

# A confirmed payment counts: In Process until the bank statement matches it, then Paid.
POSTED_PAYMENT_STATES = ("in_process", "paid")
PROFORMA_STATES = [
    ("issued", "Issued"),
    ("partial", "Partially Paid"),
    ("paid", "Paid"),
    ("invoiced", "Invoiced"),
    ("cancel", "Cancelled"),
]


class X4uSaleProforma(models.Model):
    """The one PI of an order (spec v0.8 Q1): the Salesperson makes it once the customer agrees,
    before the payment; the whole order goes by its number.

    Not a tax invoice, no journal entry: the payments are linked to the order and its PI, and the
    tax invoice of the order applies them (O8).
    """

    _name = "x4u.sale.proforma"
    _description = "Proforma Invoice"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Number", required=True, readonly=True, copy=False, index="trigram")
    sequence = fields.Integer(readonly=True, copy=False)
    order_id = fields.Many2one(
        "sale.order", string="Sales Order", required=True, readonly=True, index=True, ondelete="restrict",
        check_company=True,
    )
    payment_ids = fields.One2many(
        "account.payment", "x4u_proforma_id", string="Payments", readonly=True,
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
    amount_due = fields.Monetary(
        string="Amount Due Now", compute="_compute_amounts",
        help="The next payment of the schedule that is not paid yet (Q2).",
    )
    amount_paid = fields.Monetary(string="Paid to Date", compute="_compute_amounts")
    amount_remaining = fields.Monetary(string="Remaining", compute="_compute_amounts")
    schedule_ids = fields.One2many(related="order_id.x4u_schedule_ids", string="Payment Schedule")
    cancelled = fields.Boolean(readonly=True, copy=False)
    state = fields.Selection(PROFORMA_STATES, string="Status", compute="_compute_state", store=True, tracking=True)

    def _compute_amounts(self):
        for proforma in self:
            order = proforma.order_id.sudo()
            if proforma.cancelled:
                proforma.amount_due = proforma.amount_paid = proforma.amount_remaining = 0.0
                continue
            proforma.amount_remaining = order.x4u_amount_remaining
            proforma.amount_paid = order._x4u_amount_received()
            proforma.amount_due = order._x4u_next_amount() if order.x4u_amount_remaining else 0.0

    @api.depends(
        "cancelled",
        "payment_ids.state",
        "payment_ids.amount",
        "order_id.amount_total",
        "order_id.order_line.invoice_lines.move_id.state",
        "order_id.order_line.invoice_lines.move_id.payment_state",
    )
    def _compute_state(self):
        for proforma in self:
            order = proforma.order_id.sudo()
            if proforma.cancelled:
                proforma.state = "cancel"
            elif order._x4u_final_invoices():
                proforma.state = "invoiced"
            elif order.currency_id.is_zero(order._x4u_amount_received()):
                proforma.state = "issued"
            elif order.x4u_amount_remaining:
                proforma.state = "partial"
            else:
                proforma.state = "paid"

    @api.model_create_multi
    def create(self, vals_list):
        """One PI for the order (Q1): S012-PI, then S012-PI2 if it is made again after a cancel."""
        last = {}
        for vals in vals_list:
            order = self.env["sale.order"].browse(vals["order_id"])
            if order.state == "cancel":
                raise UserError(_("%s is cancelled.", order.name))
            if order._x4u_active_proforma() or order.id in last:
                raise UserError(_("%s already has its PI: cancel it to make a new one.", order.name))
            sequence = max(order.sudo().x4u_proforma_ids.mapped("sequence"), default=0) + 1
            last[order.id] = sequence
            vals.update(sequence=sequence, name="%s-PI%s" % (order.name, sequence if sequence > 1 else ""))
        proformas = super().create(vals_list)
        for proforma in proformas:
            proforma.order_id.sudo().message_post(
                body=_(
                    "PI %(name)s issued: %(total)s, due now %(due)s.",
                    name=proforma.name,
                    total=format_amount(self.env, proforma.amount_total, proforma.currency_id),
                    due=format_amount(self.env, proforma.amount_due, proforma.currency_id),
                )
            )
        return proformas

    @api.ondelete(at_uninstall=False)
    def _unlink_only_cancelled(self):
        if any(proforma.state != "cancel" for proforma in self):
            raise UserError(_("A PI stays with its order: cancel it instead."))

    def action_cancel(self):
        """Q4: before any payment on it, so the Salesperson can change the order and make a new one."""
        for proforma in self:
            if proforma.state != "issued":
                raise UserError(_("%s has a payment or a tax invoice: it stays.", proforma.name))
            if proforma.sudo().payment_ids.filtered(lambda p: p.state != "canceled"):
                raise UserError(_("%s has a payment: cancel the payment first.", proforma.name))
        self.write({"cancelled": True})
        for proforma in self:
            proforma.order_id.sudo().message_post(body=_("PI %s cancelled.", proforma.name))
        return True

    def action_register_payment(self):
        """Q5: the Accountant records the payment of this PI (from the order)."""
        self.ensure_one()
        return self.order_id.action_x4u_register_payment()

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

    def action_view_payments(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("account.action_account_payments")
        action.update(domain=[("x4u_proforma_id", "=", self.id)], context={"create": False})
        return action

    def x4u_next_payments(self):
        """The payments of the schedule still to come, for the PDF."""
        self.ensure_one()
        return self.schedule_ids.filtered(lambda line: line.state != "paid")

    def x4u_bank_accounts(self):
        """The company's bank accounts for the PDF (spec §6 S6)."""
        self.ensure_one()
        return self.company_id.sudo().partner_id.bank_ids
