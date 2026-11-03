from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount

# A confirmed payment counts: In Process until the bank statement matches it, then Paid.
POSTED_PAYMENT_STATES = ("in_process", "paid")
PROFORMA_STATES = [
    ("open", "Open"),
    ("paid", "Paid"),
    ("invoiced", "Invoiced"),
    ("cancel", "Cancelled"),
]


class X4uSaleProforma(models.Model):
    """One PI for the whole order, open until the last payment (spec §6 S6-S8).

    Not a tax invoice, no journal entry: the payments are linked to the sales order,
    and the tax invoice made from the PI applies them.
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
    client_order_ref = fields.Char(related="order_id.client_order_ref", string="LPO Number")
    date = fields.Date(required=True, readonly=True, default=fields.Date.context_today)
    amount_untaxed = fields.Monetary(related="order_id.amount_untaxed")
    amount_tax = fields.Monetary(related="order_id.amount_tax", string="VAT")
    amount_total = fields.Monetary(related="order_id.amount_total", string="Total")
    schedule_ids = fields.One2many("x4u.sale.schedule", "proforma_id", string="Payment Schedule")
    payment_ids = fields.One2many(
        "account.payment", "x4u_proforma_id", string="Payments", readonly=True,
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    payment_count = fields.Integer(compute="_compute_payment_count")
    amount_paid = fields.Monetary(string="Paid", compute="_compute_payment", store=True)
    state = fields.Selection(
        PROFORMA_STATES, string="Status", compute="_compute_payment", store=True, tracking=True
    )
    amount_due_now = fields.Monetary(
        string="Amount Due Now", compute="_compute_amount_due_now", inverse="_inverse_amount_due_now",
        help="The next payment of the schedule. Change it before printing to ask for another amount.",
    )
    amount_due_manual = fields.Monetary(copy=False)
    next_payment = fields.Char(string="Next Payment", compute="_compute_amount_due_now")
    cancelled = fields.Boolean(readonly=True, copy=False)

    @api.depends("payment_ids")
    def _compute_payment_count(self):
        for proforma in self:
            proforma.payment_count = len(proforma.sudo().payment_ids)

    @api.depends(
        "cancelled",
        "order_id.amount_total",
        "payment_ids.state",
        "payment_ids.amount",
        "payment_ids.currency_id",
        "order_id.order_line.invoice_lines.move_id.state",
        "order_id.order_line.invoice_lines.move_id.payment_state",
    )
    def _compute_payment(self):
        for proforma in self:
            posted = proforma.sudo().payment_ids.filtered(lambda p: p.state in POSTED_PAYMENT_STATES)
            currency = proforma.currency_id
            paid = sum(payment._x4u_amount_in(currency) for payment in posted)
            proforma.amount_paid = paid
            if proforma.cancelled:
                proforma.state = "cancel"
            elif proforma.order_id.sudo()._x4u_final_invoices():
                proforma.state = "invoiced"
            elif proforma.amount_total and currency.compare_amounts(paid, proforma.amount_total) >= 0:
                proforma.state = "paid"
            else:
                proforma.state = "open"

    @api.depends("amount_due_manual", "schedule_ids.amount_total", "schedule_ids.amount_paid", "state")
    def _compute_amount_due_now(self):
        for proforma in self:
            lines = proforma.schedule_ids
            unpaid = lines.filtered(lambda line: line.state != "paid")[:1]
            proforma.next_payment = (
                "%d/%d" % (list(lines).index(unpaid) + 1, len(lines)) if unpaid and len(lines) > 1 else ""
            )
            left = max(proforma.amount_total - proforma.order_id._x4u_amount_received(), 0.0)
            due = proforma.amount_due_manual or (unpaid.amount_total - unpaid.amount_paid if unpaid else 0.0)
            proforma.amount_due_now = min(due, left) if proforma.state == "open" else 0.0

    def _inverse_amount_due_now(self):
        for proforma in self:
            proforma.amount_due_manual = proforma.amount_due_now

    @api.model_create_multi
    def create(self, vals_list):
        """Numbered after the sales order: S012-PI, then S012-PI2 if it is made again."""
        last = {}
        for vals in vals_list:
            order = self.env["sale.order"].browse(vals["order_id"])
            if order.id not in last:
                last[order.id] = max(order.sudo().x4u_proforma_ids.mapped("sequence"), default=0)
            last[order.id] += 1
            number = last[order.id]
            vals.update(sequence=number, name="%s-PI%s" % (order.name, number if number > 1 else ""))
        proformas = super().create(vals_list)
        for proforma in proformas:
            order = proforma.order_id
            order.x4u_schedule_ids.with_context(x4u_schedule_sync=True).write({"proforma_id": proforma.id})
            order.sudo().message_post(
                body=_(
                    "PI %(name)s issued: %(amount)s in %(count)s payments (%(schedule)s)",
                    name=proforma.name,
                    amount=format_amount(self.env, proforma.amount_total, proforma.currency_id),
                    count=len(order.x4u_schedule_ids),
                    schedule=", ".join(line._x4u_label() for line in order.x4u_schedule_ids),
                )
            )
        proformas._x4u_sync_followup()
        return proformas

    @api.ondelete(at_uninstall=False)
    def _unlink_only_cancelled(self):
        if any(proforma.state != "cancel" for proforma in self):
            raise UserError(_("Cancel a PI before deleting it."))

    def _x4u_sync_followup(self):
        """S12: a to-do for the Accountant on the first due date of a payment not made yet."""
        todo = self.env.ref("mail.mail_activity_data_todo")
        for proforma in self.sudo():
            activities = proforma.activity_ids.filtered(lambda a: a.activity_type_id == todo)
            lines = proforma.schedule_ids.filtered(lambda line: line.date_due and line.state != "paid")
            if proforma.state != "open" or not lines:
                if proforma.state == "cancel" or not proforma.schedule_ids.filtered("date_due"):
                    activities.unlink()
                elif proforma.state == "invoiced":
                    activities.action_feedback(feedback=_("Tax invoice issued"))
                else:
                    activities.action_feedback(feedback=_("Paid"))
                continue
            line = lines.sorted("date_due")[0]
            summary = _(
                "Follow up %(name)s: payment %(n)s/%(count)s",
                name=proforma.name,
                n=list(proforma.schedule_ids).index(line) + 1,
                count=len(proforma.schedule_ids),
            )
            if activities:
                activities[1:].unlink()
                activities[:1].write({"date_deadline": line.date_due, "summary": summary})
            else:
                user = self.env["sale.order"]._x4u_accountant_user() or self.env.user
                proforma.activity_schedule(
                    "mail.mail_activity_data_todo", date_deadline=line.date_due, user_id=user.id, summary=summary
                )

    def action_register_payment(self):
        """S7: a draft payment for the next payment of the schedule; the Accountant confirms it."""
        self.ensure_one()
        if self.state != "open":
            raise UserError(_("%s is not open: paid, invoiced or cancelled.", self.name))
        order = self.order_id
        memo = "%s · %s" % (self.name, self.next_payment) if self.next_payment else self.name
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": order.partner_id.commercial_partner_id.id,
                "amount": self.amount_due_now,
                "currency_id": self.currency_id.id,
                "memo": memo,
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

    def action_create_tax_invoice(self):
        """S8: the tax invoice of the whole order, any time; confirming it applies the payments."""
        self.ensure_one()
        if self.state not in ("open", "paid"):
            raise UserError(_("%s is already invoiced or cancelled.", self.name))
        order = self.order_id
        if order.invoice_status != "to invoice":
            raise UserError(_("%s has nothing left to invoice.", order.name))
        before = order.invoice_ids
        self.env["sale.advance.payment.inv"].with_context(
            active_model="sale.order", active_ids=order.ids
        ).create({"advance_payment_method": "delivered"}).create_invoices()
        order.invalidate_recordset(["invoice_ids"])
        invoice = order.invoice_ids - before
        return {
            "type": "ir.actions.act_window",
            "name": _("Tax Invoice"),
            "res_model": "account.move",
            "res_id": invoice[:1].id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def action_cancel(self):
        """S13: only without a payment (cancel the payment first)."""
        for proforma in self:
            if proforma.sudo().payment_ids.filtered(lambda p: p.state not in ("canceled", "rejected")):
                raise UserError(_("%s has a payment: cancel the payment first.", proforma.name))
            if proforma.state == "invoiced":
                raise UserError(_("%s is invoiced.", proforma.name))
        self.cancelled = True
        self.schedule_ids.with_context(x4u_schedule_sync=True).write({"proforma_id": False})
        self._x4u_sync_followup()
        for proforma in self:
            proforma.order_id.sudo().message_post(body=_("PI %s cancelled.", proforma.name))

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

    def x4u_bank_accounts(self):
        """The company's bank accounts for the PDF (spec §6 S6)."""
        self.ensure_one()
        return self.company_id.sudo().partner_id.bank_ids
