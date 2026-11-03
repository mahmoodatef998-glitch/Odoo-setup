from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .x4u_payment_schedule import BEFORE_DELIVERY
from .x4u_sale_proforma import POSTED_PAYMENT_STATES, PROFORMA_STATES

PO_CHECK_STATES = [("to_check", "To Check"), ("match", "Matches"), ("mismatch", "Doesn't Match")]
PO_CHECK_FIELDS = {"x4u_po_check", "x4u_po_check_user_id", "x4u_po_check_date", "x4u_po_mismatch_reason"}
ACTIVITY_PO_CHECK = "x4u_sale.mail_activity_type_po_check"
ACTIVITY_PO_FIX = "x4u_sale.mail_activity_type_po_fix"


def x4u_own_attachments(records, field):
    """A file uploaded before the record was saved belongs to nobody, so only its uploader could
    open it: give it to the record (the Accountant opens the customer PO, Purchasing's vendor PI)."""
    for record in records:
        loose = record[field].sudo().filtered(lambda attachment: not attachment.res_id)
        if loose:
            loose.write({"res_model": record._name, "res_id": record.id})


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # §3: the LPO is the customer's PO; Confirm needs its number and file.
    client_order_ref = fields.Char(string="LPO Number")
    x4u_lpo_date = fields.Date(string="LPO Date", copy=False)
    x4u_lpo_attachment_ids = fields.Many2many(
        "ir.attachment", "x4u_sale_order_lpo_attachment_rel", "order_id", "attachment_id",
        string="LPO File", copy=False,
    )
    # §6 S5: the Accountant checks the PO against the quotation before the PI.
    x4u_po_check = fields.Selection(
        PO_CHECK_STATES, string="Customer PO Check", copy=False, readonly=True, tracking=True
    )
    x4u_po_check_user_id = fields.Many2one("res.users", string="PO Checked By", copy=False, readonly=True)
    x4u_po_check_date = fields.Datetime(string="PO Checked On", copy=False, readonly=True)
    x4u_po_mismatch_reason = fields.Text(string="Why It Doesn't Match", copy=False, readonly=True)
    # §6 S2 / S3: the payments agreed in the quotation, from the terms or Custom.
    x4u_schedule_ids = fields.One2many("x4u.sale.schedule", "order_id", string="Payment Schedule", copy=True)
    x4u_schedule_custom = fields.Boolean(related="payment_term_id.x4u_custom")
    x4u_schedule_percent = fields.Float(string="Total %", compute="_compute_x4u_schedule_percent")
    x4u_pay_before_delivery = fields.Boolean(compute="_compute_x4u_pay_before_delivery")
    # §6 S6: the Accountant's PI; salespeople see its status and the amounts only.
    x4u_proforma_ids = fields.One2many(
        "x4u.sale.proforma", "order_id", string="PIs",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    x4u_proforma_count = fields.Integer(
        compute="_compute_x4u_proforma_count", groups="account.group_account_invoice,account.group_account_readonly"
    )
    x4u_proforma_state = fields.Selection(PROFORMA_STATES, string="PI", compute="_compute_x4u_proforma_state")
    x4u_advance_payment_ids = fields.One2many(
        "account.payment", "x4u_sale_order_id", string="Advance Payments",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    x4u_advance_count = fields.Integer(compute="_compute_x4u_payments")
    x4u_amount_advance = fields.Monetary(string="Advances Received", compute="_compute_x4u_payments")
    x4u_amount_remaining = fields.Monetary(string="Remaining", compute="_compute_x4u_payments")
    x4u_final_invoice_paid = fields.Boolean(string="Final Invoice Paid", compute="_compute_x4u_payments")

    @api.depends("x4u_schedule_ids.percent")
    def _compute_x4u_schedule_percent(self):
        for order in self:
            order.x4u_schedule_percent = sum(order.x4u_schedule_ids.mapped("percent"))

    @api.depends("payment_term_id.x4u_pay_before_delivery", "payment_term_id.x4u_custom", "x4u_schedule_ids.trigger")
    def _compute_x4u_pay_before_delivery(self):
        for order in self:
            if order.payment_term_id.x4u_custom:
                triggers = order.x4u_schedule_ids.mapped("trigger")
                order.x4u_pay_before_delivery = any(trigger in BEFORE_DELIVERY for trigger in triggers)
            else:
                order.x4u_pay_before_delivery = order.payment_term_id.x4u_pay_before_delivery

    @api.depends("x4u_proforma_ids")
    def _compute_x4u_proforma_count(self):
        for order in self:
            order.x4u_proforma_count = len(order.x4u_proforma_ids)

    @api.depends("x4u_proforma_ids.state")
    def _compute_x4u_proforma_state(self):
        for order in self:
            order.x4u_proforma_state = order._x4u_active_proforma().state

    @api.depends(
        "amount_total",
        "invoice_ids.state",
        "invoice_ids.amount_residual",
        "x4u_advance_payment_ids.state",
        "x4u_advance_payment_ids.amount",
        "x4u_advance_payment_ids.move_id.line_ids.amount_residual",
    )
    def _compute_x4u_payments(self):
        """S9: what came in for the order; the Salesperson sees the amounts, not the payments."""
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

    def _x4u_amount_received(self):
        """Advances not applied yet plus what the invoices got: the schedule is paid in order."""
        self.ensure_one()
        return self.amount_total - self.x4u_amount_remaining

    def _x4u_final_invoices(self):
        """The posted tax invoices of the order (not down payments, not reversed)."""
        return self.order_line.invoice_lines.move_id.filtered(
            lambda move: move.state == "posted"
            and move.move_type == "out_invoice"
            and move.payment_state != "reversed"
            and move._x4u_is_final_invoice()
        )

    def _x4u_active_proforma(self):
        self.ensure_one()
        return self.sudo().x4u_proforma_ids.filtered(lambda proforma: proforma.state != "cancel")[:1]

    # ------------------------------------------------------------------
    # Payment schedule (S2 / S3)
    # ------------------------------------------------------------------

    def _x4u_schedule_values(self):
        self.ensure_one()
        term = self.payment_term_id
        if not term:
            return [{"sequence": 10, "percent": 100.0, "trigger": "invoice", "days": 0}]
        if term.x4u_custom:
            return [{"sequence": 10, "percent": 100.0, "trigger": "order"}]
        return self.env["x4u.sale.schedule"]._x4u_values_from_term(term)

    def _x4u_fill_schedule(self):
        for order in self:
            commands = [Command.clear()] + [Command.create(values) for values in order._x4u_schedule_values()]
            order.with_context(x4u_schedule_sync=True).write({"x4u_schedule_ids": commands})

    def _x4u_check_schedule_total(self):
        for order in self.filtered("x4u_schedule_ids"):
            if not order.currency_id.is_zero(order.x4u_schedule_percent - 100.0):
                raise ValidationError(
                    _(
                        "%(order)s: the payment schedule must add up to 100%% (now %(percent)s%%).",
                        order=order.name,
                        percent="%g" % order.x4u_schedule_percent,
                    )
                )

    def _x4u_check_schedule_editable(self):
        self.ensure_one()
        if not self.payment_term_id.x4u_custom:
            raise UserError(
                _("The payment schedule of %s comes from its payment terms: choose Custom to write your own.", self.name)
            )
        self._x4u_check_terms_editable()

    def _x4u_check_terms_editable(self):
        self.ensure_one()
        if self.locked:
            raise UserError(_("%s is locked: the Sales Manager unlocks it to change the payment terms.", self.name))
        if self._x4u_active_proforma():
            raise UserError(_("%s has a PI: the Accountant cancels it before the payment terms change.", self.name))

    def _x4u_log_schedule(self):
        for order in self:
            order.message_post(
                body=_("Payment schedule: %s", ", ".join(line._x4u_label() for line in order.x4u_schedule_ids))
            )

    @api.onchange("payment_term_id")
    def _onchange_x4u_payment_term(self):
        # The form shows the schedule of the terms; Custom keeps the lines to edit them.
        if not self.payment_term_id.x4u_custom or not self.x4u_schedule_ids:
            self.x4u_schedule_ids = [Command.clear()] + [
                Command.create(values) for values in self._x4u_schedule_values()
            ]

    @api.model_create_multi
    def create(self, vals_list):
        orders = super(SaleOrder, self.with_context(x4u_schedule_sync=True)).create(vals_list).with_env(self.env)
        for order, vals in zip(orders, vals_list):
            if not order.payment_term_id.x4u_custom or not order.x4u_schedule_ids:
                order._x4u_fill_schedule()
            elif "x4u_schedule_ids" in vals:
                order._x4u_check_schedule_total()
                order._x4u_log_schedule()
        x4u_own_attachments(orders, "x4u_lpo_attachment_ids")
        return orders

    def write(self, vals):
        if PO_CHECK_FIELDS & set(vals) and not self.env.su:
            raise self._x4u_accountant_only()
        if self.env.context.get("x4u_schedule_sync"):
            return super().write(vals)
        if "payment_term_id" in vals:
            for order in self.filtered(lambda o: o.payment_term_id.id != vals["payment_term_id"]):
                order._x4u_check_terms_editable()
        schedule = vals.get("x4u_schedule_ids")
        vals = {key: value for key, value in vals.items() if key != "x4u_schedule_ids"}
        terms = {order: order.payment_term_id for order in self}
        res = super().write(vals) if vals else True
        # A standard term decides the schedule; the form's lines only showed it.
        self.filtered(
            lambda o: o.payment_term_id != terms[o] and (not o.payment_term_id.x4u_custom or not o.x4u_schedule_ids)
        )._x4u_fill_schedule()
        if schedule is not None:
            custom = self.filtered("payment_term_id.x4u_custom")
            if custom:
                super(SaleOrder, custom).write({"x4u_schedule_ids": schedule})
                custom._x4u_check_schedule_total()
                custom._x4u_log_schedule()
        if "x4u_lpo_attachment_ids" in vals:
            x4u_own_attachments(self, "x4u_lpo_attachment_ids")
        return res

    # ------------------------------------------------------------------
    # Confirm and the customer PO check (§3, S1, S5)
    # ------------------------------------------------------------------

    def action_confirm(self):
        if not self.env.su:
            for order in self:
                missing = [
                    label
                    for label, value in (
                        (_("LPO Number"), order.client_order_ref),
                        (_("LPO File"), order.x4u_lpo_attachment_ids),
                    )
                    if not value
                ]
                if missing:
                    raise UserError(
                        _(
                            "%(order)s: attach the customer PO before confirming (missing: %(missing)s).",
                            order=order.name,
                            missing=", ".join(missing),
                        )
                    )
        self._x4u_check_schedule_total()
        res = super().action_confirm()
        self.sudo().write({"x4u_po_check": "to_check"})
        self._x4u_ask_po_check()
        return res

    @api.model
    def _x4u_accountant_only(self):
        return AccessError(_("The Accountant checks the customer PO and handles the PI and the payments."))

    def _x4u_check_accountant(self):
        if not self.env.su and not self.env.user.has_group("account.group_account_invoice"):
            raise self._x4u_accountant_only()

    def _x4u_ask_po_check(self):
        user = self._x4u_accountant_user()
        if user:
            for order in self.sudo():
                order.activity_schedule(
                    ACTIVITY_PO_CHECK, user_id=user.id, summary=_("Check the customer PO of %s", order.name)
                )

    def _x4u_po_checked(self, state, reason=False):
        self.sudo().write(
            {
                "x4u_po_check": state,
                "x4u_po_check_user_id": self.env.uid,
                "x4u_po_check_date": fields.Datetime.now(),
                "x4u_po_mismatch_reason": reason,
            }
        )

    def action_x4u_po_match(self):
        self._x4u_check_accountant()
        for order in self:
            if order.state != "sale" or order.x4u_po_check == "match":
                raise UserError(_("%s is not waiting for the customer PO check.", order.name))
        self._x4u_po_checked("match")
        self.sudo().activity_feedback([ACTIVITY_PO_CHECK], feedback=_("Matches the quotation"))
        self.sudo().activity_unlink([ACTIVITY_PO_FIX])
        for order in self:
            order.message_post(body=_("Customer PO checked: it matches the quotation."))

    def action_x4u_po_mismatch(self):
        self.ensure_one()
        self._x4u_check_accountant()
        return {
            "type": "ir.actions.act_window",
            "name": _("Customer PO Doesn't Match"),
            "res_model": "x4u.sale.po.mismatch",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_order_id": self.id},
        }

    def _x4u_po_mismatch(self, reason):
        self._x4u_check_accountant()
        for order in self:
            if order.state != "sale" or order.x4u_po_check != "to_check":
                raise UserError(_("%s is not waiting for the customer PO check.", order.name))
        self._x4u_po_checked("mismatch", reason)
        self.sudo().activity_feedback([ACTIVITY_PO_CHECK], feedback=_("Doesn't match: %s", reason))
        for order in self.sudo():
            if order.user_id:
                order.activity_schedule(
                    ACTIVITY_PO_FIX,
                    user_id=order.user_id.id,
                    summary=_("Fix %(order)s: %(reason)s", order=order.name, reason=reason),
                )
            order.message_post(body=_("Customer PO doesn't match the quotation: %s", reason))

    def action_x4u_po_recheck(self):
        """The Salesperson fixed it with the customer: back to the Accountant."""
        for order in self:
            if order.x4u_po_check != "mismatch":
                raise UserError(_("%s is not waiting for a fix of the customer PO.", order.name))
        self.sudo().write({"x4u_po_check": "to_check"})
        self.sudo().activity_feedback([ACTIVITY_PO_FIX], feedback=_("Sent back to the Accountant"))
        self._x4u_ask_po_check()
        for order in self:
            order.message_post(body=_("Customer PO sent back to the Accountant to check."))

    # ------------------------------------------------------------------
    # The PI (S6)
    # ------------------------------------------------------------------

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

    def action_x4u_create_proforma(self):
        self.ensure_one()
        self._x4u_check_accountant()
        if self.state != "sale":
            raise UserError(_("Confirm %s before its PI.", self.name))
        if self.x4u_po_check != "match":
            raise UserError(_("Check the customer PO of %s first: PO Matches Quotation.", self.name))
        if self._x4u_active_proforma():
            raise UserError(_("%s already has a PI.", self.name))
        if not self.x4u_schedule_ids:
            # An order from before the schedules: its terms give it one.
            self.sudo()._x4u_fill_schedule()
        self._x4u_check_schedule_total()
        proforma = self.env["x4u.sale.proforma"].create({"order_id": self.id})
        return proforma._x4u_open()

    def action_x4u_view_proformas(self):
        self.ensure_one()
        proformas = self.x4u_proforma_ids
        if len(proformas) == 1:
            return proformas._x4u_open()
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
