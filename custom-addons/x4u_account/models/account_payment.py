from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .account_payment_method import PDC

PDC_STATES = [
    ("draft", "Draft"),
    ("issued", "Issued"),
    ("cleared", "Cleared"),
    ("bounced", "Bounced"),
    ("canceled", "Canceled"),
]


class AccountPayment(models.Model):
    _inherit = "account.payment"

    x4u_cheque_number = fields.Char(string="Cheque Number", copy=False, tracking=True)
    x4u_cheque_date = fields.Date(
        string="Cheque Date", copy=False, tracking=True, help="The date written on the cheque: the bank pays it then."
    )
    x4u_pdc_bounced = fields.Boolean(copy=False, readonly=True)
    x4u_pdc_bounce_reason = fields.Text(string="Why It Bounced", copy=False, readonly=True)
    x4u_pdc_state = fields.Selection(
        PDC_STATES, string="Cheque Status", compute="_compute_x4u_pdc_state", store=True, index=True,
        help="Issued: given to the vendor, the money is in PDC Payable. "
        "Cleared: the bank paid it (matched with the bank statement). Bounced: the bank refused it.",
    )

    @api.depends("payment_method_line_id.code", "state", "is_matched", "x4u_pdc_bounced")
    def _compute_x4u_pdc_state(self):
        for pay in self:
            if pay.payment_method_line_id.code != PDC:
                pay.x4u_pdc_state = False
            elif pay.x4u_pdc_bounced:
                pay.x4u_pdc_state = "bounced"
            elif pay.state == "draft":
                pay.x4u_pdc_state = "draft"
            elif pay.state in ("canceled", "rejected"):
                pay.x4u_pdc_state = "canceled"
            elif pay.is_matched:
                pay.x4u_pdc_state = "cleared"
            else:
                pay.x4u_pdc_state = "issued"

    def _compute_outstanding_account_id(self):
        """A PDC waits in PDC Payable, not in Outstanding Payments, until the bank clears it."""
        res = super()._compute_outstanding_account_id()
        for pay in self:
            line = pay.payment_method_line_id
            if line.code == PDC and not line.payment_account_id:
                pay.outstanding_account_id = pay.company_id._x4u_pdc_issued_account()
        return res

    def _get_aml_default_display_name_list(self):
        """The cheque number on the entry: the bank statement shows it, so the perfect match finds the cheque."""
        terms = super()._get_aml_default_display_name_list()
        if self.payment_method_line_id.code == PDC and self.x4u_cheque_number:
            terms += [("sep", " - "), ("cheque", _("Cheque %s", self.x4u_cheque_number))]
        return terms

    def action_post(self):
        for pay in self.filtered(lambda p: p.payment_method_line_id.code == PDC):
            pay._x4u_check_cheque()
        return super().action_post()

    def _x4u_check_cheque(self):
        self.ensure_one()
        if self.payment_type != "outbound":
            raise UserError(_("PDC Cheque is for payments to vendors."))
        if not self.x4u_cheque_number or not self.x4u_cheque_date:
            raise UserError(_("Write the cheque number and the cheque date of %s.", self.display_name))
        twin = self.search(
            [
                ("id", "!=", self.id),
                ("journal_id", "=", self.journal_id.id),
                ("x4u_cheque_number", "=", self.x4u_cheque_number),
                ("x4u_pdc_state", "in", ("issued", "cleared")),
            ],
            limit=1,
        )
        if twin:
            raise UserError(
                _("Cheque %(number)s is already used on %(payment)s.", number=self.x4u_cheque_number, payment=twin.name)
            )

    def action_x4u_pdc_bounce(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Cheque Bounced"),
            "res_model": "x4u.pdc.bounce",
            "view_mode": "form",
            "target": "new",
            "context": {"default_payment_id": self.id},
        }

    def _x4u_pdc_bounce(self, reason):
        """The bank refused the cheque: the entry is cancelled and the bill is open again."""
        for pay in self:
            if pay.x4u_pdc_state != "issued":
                raise UserError(_("Only an issued cheque that the bank has not paid can bounce."))
            bills = pay.reconciled_bill_ids
            pay.action_draft()
            pay.action_cancel()
            pay.write({"x4u_pdc_bounced": True, "x4u_pdc_bounce_reason": reason})
            body = _("Cheque %(number)s bounced: %(reason)s", number=pay.x4u_cheque_number, reason=reason)
            pay.message_post(body=body)
            for bill in bills:
                bill.message_post(body=body)
