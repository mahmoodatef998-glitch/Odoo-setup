from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount

from odoo.addons.x4u_sale.models.sale_order import x4u_own_attachments
from odoo.addons.x4u_sale.models.x4u_sale_proforma import POSTED_PAYMENT_STATES

VENDOR_PI_STATES = [
    ("to_check", "To Check"),
    ("mismatch", "Doesn't Match"),
    ("open", "Open"),
    ("paid", "Paid"),
    ("billed", "Billed"),
    ("cancel", "Cancelled"),
]
CHECK_STATES = [("to_check", "To Check"), ("match", "Matches"), ("mismatch", "Doesn't Match")]
ACTIVITY_VENDOR_PI = "x4u_purchase.mail_activity_type_vendor_pi"
ACTIVITY_VENDOR_PI_FIX = "x4u_purchase.mail_activity_type_vendor_pi_fix"


class X4uPurchaseProforma(models.Model):
    """The vendor's PI for a PO, recorded and paid by the Accountant (spec P5-P8).

    Not a bill: the payments are linked to the PO, and the vendor bill of the PO applies them.
    """

    _name = "x4u.purchase.proforma"
    _description = "Vendor Proforma Invoice"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Number", readonly=True, copy=False, default="/")
    sequence = fields.Integer(readonly=True, copy=False)
    vendor_ref = fields.Char(string="Vendor PI Number", required=True, tracking=True)
    date = fields.Date(string="Vendor PI Date", required=True, default=fields.Date.context_today, tracking=True)
    attachment_ids = fields.Many2many(
        "ir.attachment", "x4u_purchase_proforma_attachment_rel", "proforma_id", "attachment_id",
        string="Vendor PI File",
    )
    order_id = fields.Many2one(
        "purchase.order", string="Purchase Order", required=True, index=True, ondelete="restrict",
        check_company=True, domain="[('state', 'in', ('purchase', 'done'))]",
    )
    partner_id = fields.Many2one(related="order_id.partner_id", string="Vendor", store=True, index=True)
    user_id = fields.Many2one(related="order_id.user_id", string="Buyer", store=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="order_id.currency_id", store=True)
    amount_untaxed = fields.Monetary(related="order_id.amount_untaxed")
    amount_tax = fields.Monetary(related="order_id.amount_tax", string="VAT")
    amount_total = fields.Monetary(related="order_id.amount_total", string="Total")
    schedule_ids = fields.One2many("x4u.purchase.schedule", "proforma_id", string="Payment Schedule")
    payment_ids = fields.One2many("account.payment", "x4u_purchase_proforma_id", string="Payments", readonly=True)
    payment_count = fields.Integer(compute="_compute_payment_count")
    check_state = fields.Selection(
        CHECK_STATES, string="Check", default="to_check", required=True, readonly=True, copy=False, tracking=True
    )
    check_user_id = fields.Many2one("res.users", string="Checked By", readonly=True, copy=False)
    check_date = fields.Datetime(string="Checked On", readonly=True, copy=False)
    mismatch_reason = fields.Text(string="Why It Doesn't Match", readonly=True, copy=False)
    amount_paid = fields.Monetary(string="Paid", compute="_compute_state", store=True)
    state = fields.Selection(VENDOR_PI_STATES, string="Status", compute="_compute_state", store=True, tracking=True)
    amount_due_now = fields.Monetary(
        string="Amount Due Now", compute="_compute_amount_due_now", inverse="_inverse_amount_due_now",
        help="The next payment of the schedule. Change it to pay another amount.",
    )
    amount_due_manual = fields.Monetary(copy=False)
    next_payment = fields.Char(string="Next Payment", compute="_compute_amount_due_now")
    cancelled = fields.Boolean(readonly=True, copy=False)

    @api.depends("payment_ids")
    def _compute_payment_count(self):
        for proforma in self:
            proforma.payment_count = len(proforma.payment_ids)

    @api.depends(
        "cancelled",
        "check_state",
        "order_id.amount_total",
        "payment_ids.state",
        "payment_ids.amount",
        "payment_ids.currency_id",
        "order_id.order_line.invoice_lines.move_id.state",
    )
    def _compute_state(self):
        for proforma in self:
            currency = proforma.currency_id
            posted = proforma.payment_ids.filtered(lambda p: p.state in POSTED_PAYMENT_STATES)
            paid = sum(payment._x4u_amount_in(currency) for payment in posted)
            proforma.amount_paid = paid
            if proforma.cancelled:
                proforma.state = "cancel"
            elif proforma.order_id._x4u_bills():
                proforma.state = "billed"
            elif proforma.check_state != "match":
                proforma.state = proforma.check_state
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
        """Numbered after the PO: PO012-VPI, then PO012-VPI2 if the vendor sends another one."""
        self.check_access("create")
        last = {}
        for vals in vals_list:
            order = self.env["purchase.order"].browse(vals["order_id"])
            if order.state not in ("purchase", "done"):
                raise UserError(_("%s is not approved yet: its vendor PI comes after the approval.", order.name))
            if order._x4u_active_proforma():
                raise UserError(_("%s already has a vendor PI: cancel it first.", order.name))
            if order.id not in last:
                last[order.id] = max(order.sudo().x4u_proforma_ids.mapped("sequence"), default=0)
            last[order.id] += 1
            number = last[order.id]
            vals.update(sequence=number, name="%s-VPI%s" % (order.name, number if number > 1 else ""))
        proformas = super().create(vals_list)
        for proforma in proformas:
            order = proforma.order_id
            if not order.x4u_schedule_ids:
                # A PO from before the schedules: its terms give it one.
                order.sudo()._x4u_fill_schedule()
            order.x4u_schedule_ids.with_context(x4u_schedule_sync=True).write({"proforma_id": proforma.id})
            order.sudo().activity_feedback([ACTIVITY_VENDOR_PI], feedback=_("Recorded: %s", proforma.name))
            order.sudo().message_post(
                body=_(
                    "Vendor PI %(ref)s recorded (%(name)s): %(amount)s",
                    ref=proforma.vendor_ref,
                    name=proforma.name,
                    amount=format_amount(self.env, proforma.amount_total, proforma.currency_id),
                )
            )
        x4u_own_attachments(proformas, "attachment_ids")
        return proformas

    def write(self, vals):
        res = super().write(vals)
        if "attachment_ids" in vals:
            x4u_own_attachments(self, "attachment_ids")
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_only_cancelled(self):
        if any(proforma.state != "cancel" for proforma in self):
            raise UserError(_("Cancel a vendor PI before deleting it."))

    def _x4u_checked(self, state, reason=False):
        self.write(
            {
                "check_state": state,
                "check_user_id": self.env.uid,
                "check_date": fields.Datetime.now(),
                "mismatch_reason": reason,
            }
        )

    def action_match(self):
        """P6: the vendor PI matches the PO, so it can be paid."""
        for proforma in self:
            if proforma.state not in ("to_check", "mismatch"):
                raise UserError(_("%s is not waiting for a check.", proforma.name))
        self._x4u_checked("match")
        for proforma in self:
            proforma.order_id.sudo().activity_unlink([ACTIVITY_VENDOR_PI_FIX])
            proforma.message_post(body=_("Vendor PI checked: it matches the PO."))

    def action_mismatch(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Vendor PI Doesn't Match"),
            "res_model": "x4u.purchase.pi.mismatch",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_proforma_id": self.id},
        }

    def _x4u_mismatch(self, reason):
        for proforma in self:
            if proforma.state != "to_check":
                raise UserError(_("%s is not waiting for a check.", proforma.name))
        self._x4u_checked("mismatch", reason)
        for proforma in self:
            order = proforma.order_id.sudo()
            if order.user_id:
                order.activity_schedule(
                    ACTIVITY_VENDOR_PI_FIX,
                    user_id=order.user_id.id,
                    summary=_("Vendor PI of %(order)s doesn't match: %(reason)s", order=order.name, reason=reason),
                )
            proforma.message_post(body=_("Vendor PI doesn't match the PO: %s", reason))

    def action_register_payment(self):
        """P7: a draft payment to the vendor for the next payment of the schedule."""
        self.ensure_one()
        if self.state != "open":
            raise UserError(_("%s is not open: check it against the PO first, or it is paid or billed.", self.name))
        order = self.order_id
        reference = "%s · %s" % (self.name, self.next_payment) if self.next_payment else self.name
        payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": order.partner_id.commercial_partner_id.id,
                "amount": self.amount_due_now,
                "currency_id": self.currency_id.id,
                "memo": "%s (%s)" % (reference, self.vendor_ref),
                "x4u_purchase_order_id": order.id,
                "x4u_purchase_proforma_id": self.id,
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
        for proforma in self:
            if proforma.payment_ids.filtered(lambda p: p.state not in ("canceled", "rejected")):
                raise UserError(_("%s has a payment: cancel the payment first.", proforma.name))
            if proforma.state == "billed":
                raise UserError(_("%s is billed.", proforma.name))
        self.cancelled = True
        self.schedule_ids.with_context(x4u_schedule_sync=True).write({"proforma_id": False})
        for proforma in self:
            proforma.order_id.sudo().message_post(body=_("Vendor PI %s cancelled.", proforma.name))

    def action_view_payments(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("account.action_account_payments_payable")
        action.update(domain=[("x4u_purchase_proforma_id", "=", self.id)], context={"create": False})
        return action


class X4uPurchasePiMismatch(models.TransientModel):
    """P6: why the vendor PI doesn't match the PO; the buyer gets a to-do."""

    _name = "x4u.purchase.pi.mismatch"
    _description = "Vendor PI Doesn't Match"

    proforma_id = fields.Many2one("x4u.purchase.proforma", string="Vendor PI", required=True, readonly=True)
    reason = fields.Text(string="What Doesn't Match", required=True)

    def action_confirm(self):
        self.ensure_one()
        self.proforma_id._x4u_mismatch(self.reason)
        return {"type": "ir.actions.act_window_close"}
