from markupsafe import escape

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .x4u_payment_schedule import BEFORE_DELIVERY
from .x4u_sale_proforma import POSTED_PAYMENT_STATES

PO_CHECK_STATES = [
    ("to_check", "To Approve"),
    ("match", "PO Matches"),
    ("mismatch", "Doesn't Match"),
]
PO_CHECK_FIELDS = {"x4u_po_check", "x4u_po_check_user_id", "x4u_po_check_date", "x4u_po_mismatch_reason"}
ACTIVITY_PO_CHECK = "x4u_sale.mail_activity_type_po_check"
ACTIVITY_PO_FIX = "x4u_sale.mail_activity_type_po_fix"
# v0.9 C1: where the order is, one bar for everybody.
STAGES = [
    ("quotation", "Quotation"),
    ("accepted", "Accepted"),
    ("with_accountant", "With Accountant"),
    ("returned", "Returned to Sales"),
    ("confirmed", "Confirmed"),
    ("cancel", "Cancelled"),
]
# v0.7 O2: what the Salesperson cannot change while the Accountant has the order.
FROZEN_FIELDS = {"order_line", "partner_id", "pricelist_id", "payment_term_id", "x4u_schedule_ids", "currency_id"}


def x4u_own_attachments(records, field):
    """A file uploaded before the record was saved belongs to nobody, so only its uploader could
    open it: give it to the record (the Accountant opens the customer PO, Purchasing's vendor PI)."""
    for record in records:
        loose = record[field].sudo().filtered(lambda attachment: not attachment.res_id)
        if loose:
            loose.write({"res_model": record._name, "res_id": record.id})


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # §3: the LPO is the customer's PO.
    client_order_ref = fields.Char(string="LPO Number")
    x4u_lpo_date = fields.Date(string="LPO Date", copy=False)
    x4u_lpo_attachment_ids = fields.Many2many(
        "ir.attachment", "x4u_sale_order_lpo_attachment_rel", "order_id", "attachment_id",
        string="LPO File", copy=False,
    )
    # v0.7 O2 / O7: the transfer receipts (or cheque copies) of the customer's payments.
    x4u_payment_proof_ids = fields.Many2many(
        "ir.attachment", "x4u_sale_order_payment_proof_rel", "order_id", "attachment_id",
        string="Payment Receipts", copy=False,
        help="The transfer receipt (or the cheque) of each payment: the first one goes to the Accountant with the "
        "customer PO; a new one later tells the Accountant to record it.",
    )
    # S5 / v0.7 O3: the Accountant checks the PO against the quotation before the Confirm.
    x4u_po_check = fields.Selection(
        PO_CHECK_STATES, string="Accountant", copy=False, readonly=True, tracking=True
    )
    x4u_po_check_user_id = fields.Many2one("res.users", string="PO Checked By", copy=False, readonly=True)
    x4u_po_check_date = fields.Datetime(string="PO Checked On", copy=False, readonly=True)
    x4u_po_mismatch_reason = fields.Text(string="Why It Doesn't Match", copy=False, readonly=True)
    x4u_advance_due = fields.Boolean(
        string="Payment with the Order", compute="_compute_x4u_advance_due",
        help="The terms ask for a payment with the order: it comes before the Accountant confirms it.",
    )
    # §6 S2 / S3: the payments agreed in the quotation, from the terms or Custom.
    x4u_schedule_ids = fields.One2many("x4u.sale.schedule", "order_id", string="Payment Schedule", copy=True)
    x4u_schedule_custom = fields.Boolean(related="payment_term_id.x4u_custom")
    x4u_schedule_percent = fields.Float(string="Total %", compute="_compute_x4u_schedule_percent")
    x4u_pay_before_delivery = fields.Boolean(compute="_compute_x4u_pay_before_delivery")
    # v0.8 Q1: the one PI of the order, the Salesperson's; a cancelled one stays in the list.
    x4u_proforma_ids = fields.One2many("x4u.sale.proforma", "order_id", string="PIs")
    x4u_proforma_count = fields.Integer(compute="_compute_x4u_proforma_count")
    x4u_proforma_id = fields.Many2one("x4u.sale.proforma", string="PI", compute="_compute_x4u_proforma_count")
    x4u_advance_payment_ids = fields.One2many(
        "account.payment", "x4u_sale_order_id", string="Advance Payments",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    x4u_advance_count = fields.Integer(compute="_compute_x4u_payments")
    x4u_amount_advance = fields.Monetary(string="Advances Received", compute="_compute_x4u_payments")
    x4u_amount_remaining = fields.Monetary(string="Remaining", compute="_compute_x4u_payments")
    x4u_final_invoice_paid = fields.Boolean(string="Final Invoice Paid", compute="_compute_x4u_payments")
    # v0.9 C1-C6: the customer accepted the quotation (Confirm Quotation by the Salesperson): the
    # prices and quantities are locked, the PI and the documents can come in any order.
    x4u_accepted_date = fields.Datetime(string="Accepted On", copy=False, readonly=True)
    x4u_accepted_user_id = fields.Many2one("res.users", string="Accepted By", copy=False, readonly=True)
    x4u_stage = fields.Selection(
        STAGES, string="Stage", compute="_compute_x4u_stage", store=True, tracking=True, index=True,
        help="Quotation: being prepared. Accepted: the customer said yes, prices locked, waiting for the PO, the "
        "payment and the documents. With Accountant: sent, the Accountant checks and confirms. Returned to Sales: "
        "the Accountant sent it back. Confirmed: open, the Job Order and the purchases start.",
    )
    x4u_document_ids = fields.One2many("x4u.sale.order.document", "order_id", string="Documents", copy=False)
    x4u_checklist_html = fields.Html(string="Checklist", compute="_compute_x4u_checklist_html", sanitize=False)

    @api.depends("state", "x4u_accepted_date", "x4u_po_check")
    def _compute_x4u_stage(self):
        for order in self:
            if order.state == "cancel":
                order.x4u_stage = "cancel"
            elif order.state == "sale":
                order.x4u_stage = "confirmed"
            elif order.x4u_po_check in ("to_check", "match"):
                order.x4u_stage = "with_accountant"
            elif order.x4u_po_check == "mismatch":
                order.x4u_stage = "returned"
            elif order.x4u_accepted_date:
                order.x4u_stage = "accepted"
            else:
                order.x4u_stage = "quotation"

    def _x4u_checklist(self):
        """v0.9 C4: (label, done) of what goes to the Accountant, from the payment terms and the customer."""
        self.ensure_one()
        items = [
            (_("Customer accepted the quotation (Confirm Quotation)"), bool(self.x4u_accepted_date)),
            (_("Customer PO: number, date and file"), bool(self.client_order_ref and self.x4u_lpo_date and self.x4u_lpo_attachment_ids)),
        ]
        if self.x4u_advance_due:
            items.append((_("PI (Send to Accountant makes it if there is none)"), bool(self._x4u_active_proforma())))
            items.append((_("Receipt of the first payment"), bool(self.x4u_payment_proof_ids)))
        documents = {document.type_id: document for document in self.x4u_document_ids}
        for doc_type in self.partner_id.commercial_partner_id.x4u_document_type_ids:
            items.append((doc_type.name, bool(documents.get(doc_type) and documents[doc_type].attachment_ids)))
        return items

    @api.depends(
        "x4u_accepted_date", "client_order_ref", "x4u_lpo_date", "x4u_lpo_attachment_ids", "x4u_advance_due",
        "x4u_payment_proof_ids", "x4u_proforma_ids.state", "x4u_document_ids.attachment_ids",
        "partner_id.commercial_partner_id.x4u_document_type_ids",
    )
    def _compute_x4u_checklist_html(self):
        for order in self:
            rows = "".join(
                '<li class="%s"><i class="fa %s me-2"></i>%s</li>'
                % ("text-success" if done else "text-danger", "fa-check-circle" if done else "fa-circle-o", escape(label))
                for label, done in order._x4u_checklist()
            )
            order.x4u_checklist_html = '<ul class="list-unstyled mb-0">%s</ul>' % rows

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

    @api.depends("x4u_schedule_ids.trigger")
    def _compute_x4u_advance_due(self):
        for order in self:
            order.x4u_advance_due = "order" in order.x4u_schedule_ids.mapped("trigger")

    @api.depends("x4u_proforma_ids.state")
    def _compute_x4u_proforma_count(self):
        for order in self:
            order.x4u_proforma_count = len(order.x4u_proforma_ids)
            order.x4u_proforma_id = order._x4u_active_proforma()

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
        """The PI of the order that is not cancelled (v0.8 Q1; the last one on older orders)."""
        self.ensure_one()
        return self.sudo().x4u_proforma_ids.filtered(lambda proforma: proforma.state != "cancel").sorted("sequence")[-1:]

    def _x4u_first_payment_received(self):
        self.ensure_one()
        return bool(self.sudo().x4u_advance_payment_ids.filtered(lambda p: p.state in POSTED_PAYMENT_STATES))

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
        proforma = self._x4u_active_proforma()
        if proforma:
            raise UserError(
                _("%(order)s has its PI %(pi)s: cancel it to change the terms.", order=self.name, pi=proforma.name)
            )

    def _x4u_log_schedule(self):
        for order in self:
            order.message_post(
                body=_("Payment schedule: %s", ", ".join(line._x4u_label() for line in order.x4u_schedule_ids))
            )

    def _x4u_sync_followup(self):
        """S12: a to-do for the Accountant on the first due date of a payment not made yet."""
        todo = self.env.ref("mail.mail_activity_data_todo")
        for order in self.sudo():
            activities = order.activity_ids.filtered(
                lambda a: a.activity_type_id == todo and (a.summary or "").startswith(_("Follow up"))
            )
            lines = order.x4u_schedule_ids.filtered(lambda line: line.date_due and line.state != "paid")
            if order.state != "sale" or not lines:
                if activities and not order.x4u_schedule_ids.filtered("date_due"):
                    activities.unlink()
                elif activities:
                    activities.action_feedback(feedback=_("Paid"))
                continue
            line = lines.sorted("date_due")[0]
            summary = _(
                "Follow up %(order)s: payment %(n)s/%(count)s",
                order=order.name,
                n=list(order.x4u_schedule_ids).index(line) + 1,
                count=len(order.x4u_schedule_ids),
            )
            if activities:
                activities[1:].unlink()
                activities[:1].write({"date_deadline": line.date_due, "summary": summary})
            else:
                user = order._x4u_accountant_user() or self.env.user
                order.activity_schedule(
                    "mail.mail_activity_data_todo", date_deadline=line.date_due, user_id=user.id, summary=summary
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
        x4u_own_attachments(orders, "x4u_payment_proof_ids")
        return orders

    def write(self, vals):
        if PO_CHECK_FIELDS & set(vals) and not self.env.su:
            raise self._x4u_accountant_only()
        if FROZEN_FIELDS & set(vals) and not self.env.su and not self._x4u_is_accountant():
            with_accountant = self.filtered(lambda o: o.state in ("draft", "sent") and o.x4u_po_check in ("to_check", "match"))
            if with_accountant:
                raise UserError(
                    _("%s is with the Accountant: ask to send it back before changing it.", ", ".join(with_accountant.mapped("name")))
                )
        # v0.9 C2: accepted by the customer, so the PI and the customer PO stay as the order:
        # nobody changes the prices or quantities (the Accountant neither) until Back to Quotation.
        if FROZEN_FIELDS & set(vals) and not self.env.su:
            self._x4u_check_not_accepted(vals)
        if FROZEN_FIELDS & set(vals) and not self.env.su and not self._x4u_is_accountant():
            # v0.8 Q4: the customer has the PI; the order stays as on it until the PI is cancelled.
            with_pi = self.filtered(lambda o: o.state in ("draft", "sent") and o._x4u_active_proforma())
            if with_pi and self._x4u_changes_the_pi(vals):
                raise UserError(
                    _(
                        "%s has its PI with the customer: cancel the PI to change the order, then make a new one.",
                        ", ".join(with_pi.mapped("name")),
                    )
                )
        if self.env.context.get("x4u_schedule_sync"):
            return super().write(vals)
        if "payment_term_id" in vals:
            for order in self.filtered(lambda o: o.payment_term_id.id != vals["payment_term_id"]):
                order._x4u_check_terms_editable()
        schedule = vals.get("x4u_schedule_ids")
        vals = {key: value for key, value in vals.items() if key != "x4u_schedule_ids"}
        terms = {order: order.payment_term_id for order in self}
        proofs = {order: order.x4u_payment_proof_ids for order in self} if "x4u_payment_proof_ids" in vals else {}
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
        if proofs:
            x4u_own_attachments(self, "x4u_payment_proof_ids")
            # v0.7 O7: a receipt of a later payment tells the Accountant.
            new = self.filtered(lambda o: o.state == "sale" and o.x4u_payment_proof_ids - proofs[o])
            new._x4u_notify_accountant_each(lambda o: _("Payment receipt for %s: check the bank and record it", o.name))
        return res

    def _x4u_check_not_accepted(self, vals=None):
        """v0.9 C2: what the customer accepted stays as it is until Back to Quotation."""
        if self.env.su or self.env.context.get("x4u_back_to_quotation"):
            return
        accepted = self.filtered(lambda o: o.state in ("draft", "sent") and o.x4u_accepted_date)
        if accepted and (vals is None or accepted._x4u_changes_the_pi(vals)):
            raise UserError(
                _(
                    "%s was accepted by the customer: press Back to Quotation to change it (its PI is cancelled).",
                    ", ".join(accepted.mapped("name")),
                )
            )

    @api.model
    def _x4u_internal_line_fields(self):
        """Fields of a line that are not on the PI (x4u_job_order adds the Supply)."""
        return set()

    def _x4u_changes_the_pi(self, vals):
        """Q4: what the customer has on the PI; the internal choices on the lines stay open."""
        if (FROZEN_FIELDS - {"order_line"}) & set(vals):
            return True
        internal = self._x4u_internal_line_fields()
        for command in vals.get("order_line") or []:
            if not (
                isinstance(command, (list, tuple)) and command[0] == Command.UPDATE and set(command[2] or {}) <= internal
            ):
                return True
        return False

    # ------------------------------------------------------------------
    # v0.7 / v0.8: the Salesperson sends the PO, the PI and the first payment, the Accountant
    # confirms (O1-O5, Q3)
    # ------------------------------------------------------------------

    def _x4u_send_problems(self, pi_comes_with_it=False):
        """What the order still needs before the Accountant gets it (O1, O2). x4u_job_order adds
        the Supply of each generator. Send to Accountant makes the PI itself (pi_comes_with_it)."""
        self.ensure_one()
        problems = []
        if self.x4u_advance_due and not self._x4u_active_proforma() and not pi_comes_with_it:
            problems.append(_("the PI (Send to Accountant makes it)"))
        if not self.client_order_ref:
            problems.append(_("the customer PO number (LPO Number)"))
        if not self.x4u_lpo_date:
            problems.append(_("the customer PO date"))
        if not self.x4u_lpo_attachment_ids:
            problems.append(_("the customer PO file"))
        if self.x4u_advance_due and not self.x4u_payment_proof_ids:
            problems.append(_("the receipt of the first payment (transfer receipt or cheque)"))
        uploaded = self.x4u_document_ids.filtered("attachment_ids").type_id
        for doc_type in self.partner_id.commercial_partner_id.x4u_document_type_ids - uploaded:
            problems.append(_("%s (Documents tab)", doc_type.name))
        return problems

    # ------------------------------------------------------------------
    # v0.9: Confirm Quotation (the customer accepted) and Back to Quotation (C1, C2, C5)
    # ------------------------------------------------------------------

    def _x4u_accept_problems(self):
        """What the quotation needs before the customer's yes locks it. x4u_job_order adds the
        chosen option and the price of each generator."""
        self.ensure_one()
        problems = []
        if not self.order_line.filtered(lambda line: not line.display_type):
            problems.append(_("at least one line"))
        return problems

    def _x4u_sync_documents(self):
        """A line on the Documents tab for each document the customer sends with its orders."""
        for order in self:
            missing = order.partner_id.commercial_partner_id.x4u_document_type_ids - order.x4u_document_ids.type_id
            if missing:
                order.env["x4u.sale.order.document"].sudo().create(
                    [{"order_id": order.id, "type_id": doc_type.id} for doc_type in missing]
                )

    def action_x4u_accept(self):
        """C1: the Salesperson, once the customer said yes. Nothing is made, bought or reserved and
        nothing is posted: only the prices and quantities are locked (C2)."""
        for order in self:
            if order.state not in ("draft", "sent") or order.x4u_accepted_date:
                raise UserError(_("%s is not a quotation to accept.", order.name))
            order._x4u_check_schedule_total()
            problems = order._x4u_accept_problems()
            if problems:
                raise UserError(
                    _("%(order)s needs before the customer's acceptance:\n- %(list)s", order=order.name, list="\n- ".join(problems))
                )
        self.sudo().write({"x4u_accepted_date": fields.Datetime.now(), "x4u_accepted_user_id": self.env.uid})
        self._x4u_sync_documents()
        for order in self:
            order.message_post(
                body=_("Accepted by the customer: the prices and quantities are locked. Next: the PI, the customer PO and the payment.")
            )
        return True

    def action_x4u_back_to_quotation(self):
        """C2: the customer changes something: the PI is cancelled and the quotation opens again."""
        for order in self:
            if order.x4u_stage not in ("accepted", "returned"):
                raise UserError(_("%s is not an accepted quotation.", order.name))
            # Raises if a payment came in on it: the Accountant cancels the payment first.
            order.x4u_proforma_ids.filtered(lambda pi: pi.state != "cancel").with_context(x4u_back_to_quotation=True).action_cancel()
        self.sudo().write(
            {"x4u_accepted_date": False, "x4u_accepted_user_id": False, "x4u_po_check": False, "x4u_po_mismatch_reason": False}
        )
        self.sudo().activity_feedback([ACTIVITY_PO_FIX], feedback=_("Back to quotation"))
        for order in self:
            order.message_post(body=_("Back to quotation: the PI is cancelled, the order can be changed."))
        return True

    def action_x4u_send_to_accountant(self):
        """O2 / Q3: the Salesperson sends the customer PO, the PI and the first payment to the Accountant."""
        for order in self:
            if order.state not in ("draft", "sent") or order.x4u_po_check in ("to_check", "match"):
                raise UserError(_("%s is not a quotation to send to the Accountant.", order.name))
            # v0.9 C6: the customer PO came first: sending it means the customer accepted.
            if not order.x4u_accepted_date:
                order.action_x4u_accept()
            order._x4u_check_schedule_total()
            problems = order._x4u_send_problems(pi_comes_with_it=True)
            if problems:
                raise UserError(
                    _("%(order)s needs before it goes to the Accountant:\n- %(list)s", order=order.name, list="\n- ".join(problems))
                )
            # The user, 2026-11-26 (fewer steps): the PI comes with it, no separate Create PI - made
            # only once everything else is there, so a refused send leaves no PI behind.
            if order.x4u_advance_due and not order._x4u_active_proforma():
                order.action_x4u_create_proforma()
        self.sudo().write({"x4u_po_check": "to_check", "x4u_po_mismatch_reason": False})
        self.sudo().activity_feedback([ACTIVITY_PO_FIX], feedback=_("Sent back to the Accountant"))
        self._x4u_ask_po_check()
        for order in self:
            proforma = order._x4u_active_proforma()
            order.message_post(
                body=_(
                    "Sent to the Accountant: customer PO %(po)s, %(pi)s and the first payment.",
                    po=order.client_order_ref,
                    pi=proforma.name or _("no PI"),
                )
            )

    @api.model
    def _x4u_accountant_only(self):
        return AccessError(_("The Accountant checks the customer PO, records the payments and confirms the order."))

    def _x4u_is_accountant(self):
        return self.env.user.has_group("account.group_account_invoice")

    def _x4u_check_accountant(self):
        if not self.env.su and not self._x4u_is_accountant():
            raise self._x4u_accountant_only()

    def _x4u_ask_po_check(self):
        user = self._x4u_accountant_user()
        if user:
            for order in self.sudo():
                order.activity_schedule(
                    ACTIVITY_PO_CHECK, user_id=user.id,
                    summary=_("Check %s: customer PO, PI and first payment", order.name),
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
            # A confirmed order still "To Approve" is one confirmed before v0.7: its PO is checked too.
            if order.state == "cancel" or order.x4u_po_check != "to_check":
                raise UserError(_("%s is not waiting for the Accountant.", order.name))
        self._x4u_po_checked("match")
        self.sudo().activity_unlink([ACTIVITY_PO_FIX])
        for order in self:
            order.message_post(body=_("Customer PO checked: it matches the quotation."))

    def action_x4u_check_confirm(self):
        """The user, 2026-11-26 (fewer steps): PO Matches, the payment and Confirm in one screen."""
        self.ensure_one()
        self._x4u_check_accountant()
        if self.state not in ("draft", "sent") or self.x4u_po_check != "to_check":
            raise UserError(_("%s is not waiting for the Accountant.", self.name))
        return self.env["x4u.sale.check.confirm"]._x4u_action(self)

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
        """O3: back to the Salesperson, who fixes it with the customer and sends it again."""
        self._x4u_check_accountant()
        for order in self:
            if order.state not in ("draft", "sent") or order.x4u_po_check not in ("to_check", "match"):
                raise UserError(_("%s is not waiting for the Accountant.", order.name))
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

    def action_confirm(self):
        """O5: the Accountant confirms, once the PO matches and the first payment came in; the
        order opens with the Salesperson's choices."""
        if not self.env.su:
            self._x4u_check_accountant()
            for order in self:
                if order.x4u_po_check != "match":
                    raise UserError(_("%s: check the customer PO first (PO Matches Quotation).", order.name))
                if order.x4u_advance_due and not order._x4u_first_payment_received():
                    raise UserError(_("%s: record the first payment before confirming it.", order.name))
                problems = order._x4u_send_problems()
                if problems:
                    raise UserError(_("%(order)s still needs:\n- %(list)s", order=order.name, list="\n- ".join(problems)))
        self._x4u_check_schedule_total()
        # The Accountant has no Sales rights (quotation templates, routes...): once the checks
        # above pass, Odoo's own confirmation runs with full rights; the chatter keeps his name.
        res = super(SaleOrder, self.sudo()).action_confirm()
        self.sudo().activity_feedback([ACTIVITY_PO_CHECK], feedback=_("Confirmed"))
        self._x4u_sync_followup()
        return res

    # ------------------------------------------------------------------
    # Payments, PIs and the tax invoice (O4, O6, O8)
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

    def _x4u_notify_accountant_each(self, summary):
        for order in self:
            order._x4u_notify_accountant(summary(order))

    def _x4u_next_amount(self):
        """The next payment of the schedule not made yet, or what is left."""
        self.ensure_one()
        line = self.x4u_schedule_ids.filtered(lambda l: l.state != "paid")[:1]
        left = self.x4u_amount_remaining
        due = line.amount_total - line.amount_paid if line else left
        return min(due, left) if left else due

    def action_x4u_register_payment(self):
        """O4: the Accountant records a payment of the order (a draft to confirm); confirming it
        issues its PI."""
        self.ensure_one()
        self._x4u_check_accountant()
        if self.state == "cancel" or (self.state != "sale" and self.x4u_po_check not in ("to_check", "match")):
            raise UserError(_("%s is not with the Accountant.", self.name))
        number = len(self.sudo().x4u_advance_payment_ids.filtered(lambda p: p.state in POSTED_PAYMENT_STATES)) + 1
        proforma = self._x4u_active_proforma()
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_id.commercial_partner_id.id,
                "amount": self._x4u_next_amount(),
                "currency_id": self.currency_id.id,
                "memo": "%s · %s/%s" % (proforma.name or self.name, number, len(self.x4u_schedule_ids) or 1),
                "x4u_sale_order_id": self.id,
                "x4u_proforma_id": proforma.id,
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

    def action_x4u_create_tax_invoice(self):
        """O8 (S8): the tax invoice of the whole order; confirming it applies the payments."""
        self.ensure_one()
        self._x4u_check_accountant()
        if self.state != "sale" or self.invoice_status != "to invoice":
            raise UserError(_("%s has nothing left to invoice.", self.name))
        before = self.invoice_ids
        self.env["sale.advance.payment.inv"].with_context(
            active_model="sale.order", active_ids=self.ids
        ).create({"advance_payment_method": "delivered"}).create_invoices()
        self.invalidate_recordset(["invoice_ids"])
        invoice = self.invoice_ids - before
        # The user, 2026-11-26 (fewer steps): created and confirmed in one click; confirming it applies
        # the payments (and, with x4u_job_order, delivers the generators still in stock).
        invoice.filtered(lambda move: move.state == "draft").action_post()
        return {
            "type": "ir.actions.act_window",
            "name": _("Tax Invoice"),
            "res_model": "account.move",
            "res_id": invoice[:1].id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def action_x4u_due_dates(self):
        """S12: the Accountant sets a due date on each payment of the schedule (a list of its own,
        not a second list on the order form: that one broke saving a new quotation)."""
        self.ensure_one()
        self._x4u_check_accountant()
        return {
            "type": "ir.actions.act_window",
            "name": _("Due Dates · %s", self.name),
            "res_model": "x4u.sale.schedule",
            "view_mode": "list",
            "views": [(self.env.ref("x4u_sale.x4u_sale_schedule_due_view_list").id, "list")],
            "domain": [("order_id", "=", self.id)],
            "context": {"create": False, "delete": False},
            "target": "new",
        }

    def action_x4u_create_proforma(self):
        """v0.8 Q1: the Salesperson makes the PI of the order once the customer agrees."""
        self.ensure_one()
        # v0.9 C3: the PI is the accepted order; a quotation is accepted on the way.
        if not self.x4u_accepted_date:
            self.action_x4u_accept()
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


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # v0.9 C2: a line edited on its own (not through the order) is locked the same way.
    _X4U_LOCKED_LINE_FIELDS = {
        "product_id", "product_uom_qty", "product_uom", "price_unit", "discount", "tax_id", "display_type",
    }

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if not self.env.su:
            lines.order_id._x4u_check_not_accepted()
        return lines

    def write(self, vals):
        if self._X4U_LOCKED_LINE_FIELDS & set(vals) and not self.env.su:
            self.order_id._x4u_check_not_accepted()
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            self.order_id._x4u_check_not_accepted()
        return super().unlink()
