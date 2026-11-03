from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.x4u_sale.models.sale_order import x4u_own_attachments
from odoo.addons.x4u_sale.models.x4u_sale_proforma import POSTED_PAYMENT_STATES

from .x4u_purchase_proforma import ACTIVITY_VENDOR_PI, VENDOR_PI_STATES

# P3 (blueprint J15, form P00947): how we pay; "cheque at 60 days" = PDC + 60 Days.
PAYMENT_MODES = [("cash", "Cash"), ("pdc", "PDC (post-dated cheque)"), ("transfer", "Bank Transfer")]
APPROVED_STATES = ("purchase", "done")


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    x4u_payment_mode = fields.Selection(PAYMENT_MODES, string="Payment Mode", tracking=True)
    x4u_schedule_ids = fields.One2many("x4u.purchase.schedule", "order_id", string="Payment Schedule", copy=True)
    x4u_schedule_custom = fields.Boolean(related="payment_term_id.x4u_custom")
    x4u_schedule_percent = fields.Float(string="Total %", compute="_compute_x4u_schedule_percent")
    # P5: Purchasing attaches the PI the vendor sent; the Accountant records it and pays.
    x4u_vendor_pi_attachment_ids = fields.Many2many(
        "ir.attachment", "x4u_purchase_order_vendor_pi_rel", "order_id", "attachment_id",
        string="Vendor PI File", copy=False,
    )
    x4u_proforma_ids = fields.One2many(
        "x4u.purchase.proforma", "order_id", string="Vendor PIs",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    x4u_proforma_count = fields.Integer(
        compute="_compute_x4u_proforma_count", groups="account.group_account_invoice,account.group_account_readonly"
    )
    x4u_proforma_state = fields.Selection(VENDOR_PI_STATES, string="Vendor PI", compute="_compute_x4u_proforma_state")
    x4u_advance_payment_ids = fields.One2many(
        "account.payment", "x4u_purchase_order_id", string="Advance Payments",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    x4u_advance_count = fields.Integer(compute="_compute_x4u_payments")
    x4u_amount_advance = fields.Monetary(string="Advances Paid", compute="_compute_x4u_payments")
    x4u_amount_remaining = fields.Monetary(string="Remaining", compute="_compute_x4u_payments")

    @api.depends("x4u_schedule_ids.percent")
    def _compute_x4u_schedule_percent(self):
        for order in self:
            order.x4u_schedule_percent = sum(order.x4u_schedule_ids.mapped("percent"))

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
        """P11: what we paid for the PO; Purchasing sees the amounts, not the payments."""
        for order in self:
            sudo_order = order.sudo()
            currency = order.currency_id
            payments = sudo_order.x4u_advance_payment_ids.filtered(lambda p: p.state in POSTED_PAYMENT_STATES)
            bills = sudo_order.invoice_ids.filtered(lambda m: m.state == "posted" and m.move_type == "in_invoice")
            # An applied advance shows on the bill it paid, so only its open part counts here.
            unapplied = sum(payment._x4u_unapplied_in(currency) for payment in payments)
            paid_on_bills = sum(bill.amount_total - bill.amount_residual for bill in bills)
            order.x4u_advance_count = len(sudo_order.x4u_advance_payment_ids)
            order.x4u_amount_advance = sum(payment._x4u_amount_in(currency) for payment in payments)
            order.x4u_amount_remaining = max(currency.round(order.amount_total - unapplied - paid_on_bills), 0.0)

    def _x4u_amount_received(self):
        """What the vendor got (advances and bill payments): the schedule is paid in order."""
        self.ensure_one()
        return self.amount_total - self.x4u_amount_remaining

    def _x4u_bills(self):
        return self.order_line.invoice_lines.move_id.filtered(
            lambda move: move.state == "posted" and move.move_type == "in_invoice"
        )

    def _x4u_active_proforma(self):
        self.ensure_one()
        return self.sudo().x4u_proforma_ids.filtered(lambda proforma: proforma.state != "cancel")[:1]

    # ------------------------------------------------------------------
    # Payment terms and schedule (P1-P4)
    # ------------------------------------------------------------------

    def _x4u_schedule_values(self):
        self.ensure_one()
        term = self.payment_term_id
        if not term:
            return [{"sequence": 10, "percent": 100.0, "trigger": "invoice", "days": 0}]
        if term.x4u_custom:
            return [{"sequence": 10, "percent": 100.0, "trigger": "order"}]
        return self.env["x4u.purchase.schedule"]._x4u_values_from_term(term)

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
        if self.state in APPROVED_STATES:
            raise UserError(_("%s is approved: its payment terms are what the General Manager approved.", self.name))

    def _x4u_log_schedule(self):
        for order in self:
            order.message_post(
                body=_("Payment schedule: %s", ", ".join(line._x4u_label() for line in order.x4u_schedule_ids))
            )

    @api.onchange("payment_term_id")
    def _onchange_x4u_payment_term(self):
        if not self.payment_term_id.x4u_custom or not self.x4u_schedule_ids:
            self.x4u_schedule_ids = [Command.clear()] + [
                Command.create(values) for values in self._x4u_schedule_values()
            ]

    @api.model_create_multi
    def create(self, vals_list):
        orders = super(PurchaseOrder, self.with_context(x4u_schedule_sync=True)).create(vals_list).with_env(self.env)
        for order, vals in zip(orders, vals_list):
            if not order.payment_term_id.x4u_custom or not order.x4u_schedule_ids:
                order._x4u_fill_schedule()
            elif "x4u_schedule_ids" in vals:
                order._x4u_check_schedule_total()
                order._x4u_log_schedule()
        x4u_own_attachments(orders, "x4u_vendor_pi_attachment_ids")
        return orders

    def write(self, vals):
        if self.env.context.get("x4u_schedule_sync"):
            return super().write(vals)
        if not self.env.su:
            for order in self:
                if "payment_term_id" in vals and order.payment_term_id.id != vals["payment_term_id"]:
                    order._x4u_check_terms_editable()
                if "x4u_payment_mode" in vals and order.x4u_payment_mode != vals["x4u_payment_mode"]:
                    order._x4u_check_terms_editable()
        schedule = vals.get("x4u_schedule_ids")
        vals = {key: value for key, value in vals.items() if key != "x4u_schedule_ids"}
        terms = {order: order.payment_term_id for order in self}
        files = {order: order.x4u_vendor_pi_attachment_ids for order in self}
        res = super().write(vals) if vals else True
        # A standard term decides the schedule; the form's lines only showed it.
        self.filtered(
            lambda o: o.payment_term_id != terms[o] and (not o.payment_term_id.x4u_custom or not o.x4u_schedule_ids)
        )._x4u_fill_schedule()
        if schedule is not None:
            custom = self.filtered("payment_term_id.x4u_custom")
            if custom:
                super(PurchaseOrder, custom).write({"x4u_schedule_ids": schedule})
                custom._x4u_check_schedule_total()
                custom._x4u_log_schedule()
        if "x4u_vendor_pi_attachment_ids" in vals:
            x4u_own_attachments(self, "x4u_vendor_pi_attachment_ids")
            self.filtered(lambda o: o.x4u_vendor_pi_attachment_ids - files[o])._x4u_ask_vendor_pi()
        return res

    def button_confirm(self):
        self._x4u_check_schedule_total()
        return super().button_confirm()

    # ------------------------------------------------------------------
    # The vendor PI (P5, P12)
    # ------------------------------------------------------------------

    def _x4u_ask_vendor_pi(self):
        """P12: Purchasing attached the vendor's PI, so the Accountant records it and pays."""
        user = self.env["sale.order"]._x4u_accountant_user()
        activity_type = self.env.ref(ACTIVITY_VENDOR_PI)
        for order in self.sudo():
            if not user or order._x4u_active_proforma():
                continue
            if order.activity_ids.filtered(lambda a: a.activity_type_id == activity_type):
                continue
            order.activity_schedule(
                ACTIVITY_VENDOR_PI, user_id=user.id, summary=_("Record and pay the vendor PI of %s", order.name)
            )

    def action_x4u_record_vendor_pi(self):
        self.ensure_one()
        self.env["sale.order"]._x4u_check_accountant()
        if self.state not in APPROVED_STATES:
            raise UserError(_("%s is not approved yet.", self.name))
        if self._x4u_active_proforma():
            raise UserError(_("%s already has a vendor PI.", self.name))
        return {
            "type": "ir.actions.act_window",
            "name": _("Vendor PI"),
            "res_model": "x4u.purchase.proforma",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
            "context": {
                "default_order_id": self.id,
                "default_vendor_ref": self.partner_ref,
                "default_attachment_ids": [Command.set(self.x4u_vendor_pi_attachment_ids.ids)],
            },
        }

    def action_x4u_view_vendor_pis(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("x4u_purchase.x4u_purchase_proforma_action")
        proformas = self.x4u_proforma_ids
        if len(proformas) == 1:
            action.update(views=[(False, "form")], res_id=proformas.id)
        else:
            action.update(domain=[("order_id", "=", self.id)], context={"create": False})
        return action

    def action_x4u_view_advances(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("account.action_account_payments_payable")
        action.update(domain=[("x4u_purchase_order_id", "=", self.id)], context={"create": False})
        return action
