from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount

# A confirmed payment counts: In Process until the bank statement matches it, then Paid.
POSTED_PAYMENT_STATES = ("in_process", "paid")
PROFORMA_STATES = [
    ("not_paid", "Not Paid"),
    ("partial", "Partially Paid"),
    ("paid", "Paid"),
    ("cancel", "Cancelled"),
]


class X4uSaleProforma(models.Model):
    """A request for an advance: not a tax invoice, no journal entry (spec §6 B2/B3).

    The money comes in as a payment linked to the sales order; the final invoice of
    the order applies it (B6).
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
    partner_id = fields.Many2one(related="order_id.partner_id", string="Customer", store=True, index=True)
    user_id = fields.Many2one(related="order_id.user_id", string="Salesperson", store=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="order_id.currency_id", store=True)
    date = fields.Date(required=True, readonly=True, default=fields.Date.context_today)
    date_due = fields.Date(string="Due Date", tracking=True)
    percent = fields.Float(string="Percentage", digits=(16, 2), readonly=True)
    amount_untaxed = fields.Monetary(string="Untaxed Amount", readonly=True)
    amount_tax = fields.Monetary(string="VAT", readonly=True)
    amount_total = fields.Monetary(string="Total", readonly=True)
    payment_ids = fields.One2many(
        "account.payment", "x4u_proforma_id", string="Payments", readonly=True,
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    payment_count = fields.Integer(compute="_compute_payment_count")
    amount_paid = fields.Monetary(string="Paid", compute="_compute_payment", store=True)
    state = fields.Selection(
        PROFORMA_STATES, string="Status", compute="_compute_payment", store=True, tracking=True
    )
    cancelled = fields.Boolean(readonly=True, copy=False)

    @api.depends("payment_ids")
    def _compute_payment_count(self):
        for proforma in self:
            proforma.payment_count = len(proforma.sudo().payment_ids)

    @api.depends("cancelled", "amount_total", "payment_ids.state", "payment_ids.amount", "payment_ids.currency_id")
    def _compute_payment(self):
        for proforma in self:
            posted = proforma.sudo().payment_ids.filtered(lambda p: p.state in POSTED_PAYMENT_STATES)
            currency = proforma.currency_id
            paid = sum(payment._x4u_amount_in(currency) for payment in posted)
            proforma.amount_paid = paid
            if proforma.cancelled:
                proforma.state = "cancel"
            elif proforma.amount_total and currency.compare_amounts(paid, proforma.amount_total) >= 0:
                proforma.state = "paid"
            elif not currency.is_zero(paid):
                proforma.state = "partial"
            else:
                proforma.state = "not_paid"

    @api.model_create_multi
    def create(self, vals_list):
        """Numbered after the sales order: S007-PF1, S007-PF2 (no new sequence)."""
        last = {}
        for vals in vals_list:
            order = self.env["sale.order"].browse(vals["order_id"])
            if order.id not in last:
                last[order.id] = max(order.sudo().x4u_proforma_ids.mapped("sequence"), default=0)
            last[order.id] += 1
            vals.update(sequence=last[order.id], name="%s-PF%d" % (order.name, last[order.id]))
        proformas = super().create(vals_list)
        for proforma in proformas:
            proforma.order_id.sudo().message_post(
                body=_(
                    "Proforma %(name)s issued: %(percent)s%% = %(amount)s",
                    name=proforma.name,
                    percent="%g" % proforma.percent,
                    amount=format_amount(self.env, proforma.amount_total, proforma.currency_id),
                )
            )
        proformas._x4u_sync_followup()
        return proformas

    def write(self, vals):
        res = super().write(vals)
        if "date_due" in vals:
            self._x4u_sync_followup()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_only_cancelled(self):
        if any(proforma.state != "cancel" for proforma in self):
            raise UserError(_("Cancel a proforma before deleting it."))

    def _x4u_sync_followup(self):
        """B8: a to-do for the Accountant on the due date while the proforma is not paid."""
        todo = self.env.ref("mail.mail_activity_data_todo")
        for proforma in self.sudo():
            activities = proforma.activity_ids.filtered(lambda a: a.activity_type_id == todo)
            if proforma.state == "paid":
                activities.action_feedback(feedback=_("Paid"))
            elif proforma.state == "cancel" or not proforma.date_due:
                activities.unlink()
            elif activities:
                activities.date_deadline = proforma.date_due
            else:
                user = self.env["sale.order"]._x4u_accountant_user() or self.env.user
                proforma.activity_schedule(
                    "mail.mail_activity_data_todo",
                    date_deadline=proforma.date_due,
                    user_id=user.id,
                    summary=_("Follow up Proforma %s", proforma.name),
                )

    def action_register_payment(self):
        """B4: a draft payment filled in from the proforma; the Accountant confirms it."""
        self.ensure_one()
        if self.state not in ("not_paid", "partial"):
            raise UserError(_("Proforma %s is already paid or cancelled.", self.name))
        order = self.order_id
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": order.partner_id.commercial_partner_id.id,
                "amount": self.amount_total - self.amount_paid,
                "currency_id": self.currency_id.id,
                "memo": self.name,
                "x4u_sale_order_id": order.id,
                "x4u_proforma_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Register Payment"),
            "res_model": "account.payment",
            "res_id": payment.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def action_cancel(self):
        """B11: only without a payment (cancel the payment first)."""
        for proforma in self:
            if proforma.sudo().payment_ids.filtered(lambda p: p.state not in ("canceled", "rejected")):
                raise UserError(_("Proforma %s has a payment: cancel the payment first.", proforma.name))
        self.cancelled = True
        self._x4u_sync_followup()
        for proforma in self:
            proforma.order_id.sudo().message_post(body=_("Proforma %s cancelled.", proforma.name))

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

    def action_view_payments(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("account.action_account_payments")
        action.update(domain=[("x4u_proforma_id", "=", self.id)], context={"create": False})
        return action

    def x4u_bank_accounts(self):
        """The company's bank accounts for the PDF (spec §6 B3)."""
        self.ensure_one()
        return self.company_id.sudo().partner_id.bank_ids


class X4uSaleProformaWizard(models.TransientModel):
    _name = "x4u.sale.proforma.wizard"
    _description = "Issue a Proforma"

    order_id = fields.Many2one("sale.order", string="Sales Order", required=True, readonly=True)
    currency_id = fields.Many2one(related="order_id.currency_id")
    order_amount_total = fields.Monetary(related="order_id.amount_total", string="Order Total")
    requested_amount = fields.Monetary(string="Already Requested", compute="_compute_amounts")
    advance_type = fields.Selection(
        [("percentage", "Percentage"), ("fixed", "Fixed amount")],
        string="Ask For", default="percentage", required=True,
    )
    percent = fields.Float(string="Percentage", digits=(16, 2))
    fixed_amount = fields.Monetary(string="Amount Before VAT")
    date_due = fields.Date(string="Due Date")
    amount_untaxed = fields.Monetary(string="Untaxed Amount", compute="_compute_amounts")
    amount_tax = fields.Monetary(string="VAT", compute="_compute_amounts")
    amount_total = fields.Monetary(string="Total", compute="_compute_amounts")

    def _x4u_ratio(self):
        order = self.order_id
        if self.advance_type == "fixed":
            return self.fixed_amount / order.amount_untaxed if order.amount_untaxed else 0.0
        return self.percent / 100.0

    @api.depends("order_id", "advance_type", "percent", "fixed_amount")
    def _compute_amounts(self):
        for wizard in self:
            order = wizard.order_id
            untaxed, tax = order._x4u_advance_amounts(wizard._x4u_ratio())
            wizard.amount_untaxed = untaxed
            wizard.amount_tax = tax
            wizard.amount_total = untaxed + tax
            wizard.requested_amount = sum(
                order.x4u_proforma_ids.filtered(lambda p: p.state != "cancel").mapped("amount_total")
            )

    def action_confirm(self):
        self.ensure_one()
        order = self.order_id
        if order.state != "sale":
            raise UserError(_("Confirm %s before asking for an advance.", order.name))
        ratio = self._x4u_ratio()
        if ratio <= 0:
            raise UserError(_("Enter the percentage or the amount of this advance."))
        untaxed, tax = order._x4u_advance_amounts(ratio)
        requested = sum(order.x4u_proforma_ids.filtered(lambda p: p.state != "cancel").mapped("amount_untaxed"))
        if order.currency_id.compare_amounts(requested + untaxed, order.amount_untaxed) > 0:
            raise UserError(
                _(
                    "%(order)s: the proformas would ask for %(asked)s before VAT, more than the order (%(total)s).",
                    order=order.name,
                    asked=format_amount(self.env, requested + untaxed, order.currency_id),
                    total=format_amount(self.env, order.amount_untaxed, order.currency_id),
                )
            )
        proforma = self.env["x4u.sale.proforma"].create(
            {
                "order_id": order.id,
                "percent": ratio * 100.0,
                "amount_untaxed": untaxed,
                "amount_tax": tax,
                "amount_total": untaxed + tax,
                "date_due": self.date_due,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "x4u.sale.proforma",
            "res_id": proforma.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }
