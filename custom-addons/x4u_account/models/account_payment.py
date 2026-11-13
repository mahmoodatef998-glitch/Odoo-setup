from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

from .account_payment_method import PDC

PDC_STATES = [
    ("draft", "Draft"),
    ("issued", "Issued"),
    ("received", "In Hand"),
    ("deposited", "Deposited"),
    ("cleared", "Cleared"),
    ("bounced", "Bounced"),
    ("canceled", "Canceled"),
]
# The cheque can still bounce: the bank has not paid it.
OPEN_PDC_STATES = ("issued", "received", "deposited")


class AccountPayment(models.Model):
    _inherit = "account.payment"

    x4u_cheque_number = fields.Char(string="Cheque Number", copy=False, tracking=True)
    x4u_cheque_date = fields.Date(
        string="Cheque Date", copy=False, tracking=True, help="The date written on the cheque: the bank pays it then."
    )
    x4u_pdc_bounced = fields.Boolean(copy=False, readonly=True)
    x4u_pdc_bounce_reason = fields.Text(string="Why It Bounced", copy=False, readonly=True)
    x4u_pdc_bounce_move_id = fields.Many2one(
        "account.move", string="Bounce Entry", copy=False, readonly=True,
        help="Dr Customer / Cr Bank: the deposited cheque came back unpaid (spec §12 K5).",
    )
    x4u_is_received_cheque = fields.Boolean(
        string="Customer Cheque", compute="_compute_x4u_is_received_cheque", store=True,
        help="Received from a customer into the PDC Received journal (spec §12).",
    )
    x4u_is_cheque = fields.Boolean(compute="_compute_x4u_is_cheque")
    x4u_deposit_line_ids = fields.One2many(
        "account.move.line", "x4u_deposit_payment_id", string="Deposit Lines", readonly=True,
        help="This cheque's line on the bank side of the deposit entry: the bank statement clears it.",
    )
    x4u_check_deposit_id = fields.Many2one(
        "account.check.deposit", string="Deposit", compute="_compute_x4u_check_deposit_id"
    )
    x4u_pdc_state = fields.Selection(
        PDC_STATES, string="Cheque Status", compute="_compute_x4u_pdc_state", store=True, index=True,
        help="Vendor cheques - Issued: given to the vendor, the money is in PDC Payable. "
        "Customer cheques - In Hand: in PDC Received, waiting for its date; Deposited: given to the bank. "
        "Cleared: the bank paid it (matched with the bank statement). Bounced: the bank refused it.",
    )

    @api.depends("payment_type", "journal_id", "company_id.x4u_pdc_received_journal_id")
    def _compute_x4u_is_received_cheque(self):
        for pay in self:
            journal = pay.company_id.x4u_pdc_received_journal_id
            pay.x4u_is_received_cheque = bool(journal) and pay.payment_type == "inbound" and pay.journal_id == journal

    @api.depends("payment_method_line_id.code", "x4u_is_received_cheque")
    def _compute_x4u_is_cheque(self):
        for pay in self:
            pay.x4u_is_cheque = pay.payment_method_line_id.code == PDC or pay.x4u_is_received_cheque

    @api.depends("move_id.line_ids.check_deposit_id")
    def _compute_x4u_check_deposit_id(self):
        for pay in self:
            pay.x4u_check_deposit_id = pay.move_id.line_ids.check_deposit_id[:1]

    @api.depends(
        "payment_method_line_id.code",
        "state",
        "is_matched",
        "x4u_pdc_bounced",
        "x4u_is_received_cheque",
        "x4u_deposit_line_ids.parent_state",
        "x4u_deposit_line_ids.reconciled",
    )
    def _compute_x4u_pdc_state(self):
        for pay in self:
            if pay.payment_method_line_id.code != PDC and not pay.x4u_is_received_cheque:
                pay.x4u_pdc_state = False
            elif pay.x4u_pdc_bounced:
                pay.x4u_pdc_state = "bounced"
            elif pay.state == "draft":
                pay.x4u_pdc_state = "draft"
            elif pay.state in ("canceled", "rejected"):
                pay.x4u_pdc_state = "canceled"
            elif pay.x4u_is_received_cheque:
                deposit_lines = pay.x4u_deposit_line_ids.filtered(lambda line: line.parent_state == "posted")
                if not deposit_lines:
                    pay.x4u_pdc_state = "received"
                elif all(deposit_lines.mapped("reconciled")):
                    pay.x4u_pdc_state = "cleared"
                else:
                    pay.x4u_pdc_state = "deposited"
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
        if self.x4u_is_cheque and self.x4u_cheque_number:
            terms += [("sep", " - "), ("cheque", _("Cheque %s", self.x4u_cheque_number))]
        return terms

    def action_post(self):
        for pay in self.filtered("x4u_is_cheque"):
            pay._x4u_check_cheque()
        return super().action_post()

    def _x4u_check_cheque(self):
        self.ensure_one()
        if not self.x4u_is_received_cheque and self.payment_type != "outbound":
            raise UserError(
                _("PDC Cheque is for payments to vendors. A customer's cheque goes in the %s journal.",
                  self.company_id.x4u_pdc_received_journal_id.display_name or _("PDC Received"))
            )
        if not self.x4u_cheque_number or not self.x4u_cheque_date:
            raise UserError(_("Write the cheque number and the cheque date of %s.", self.display_name))
        if self.x4u_is_received_cheque:
            # Customers' cheques come from many banks: the same number can exist for two customers.
            domain = [
                ("x4u_is_received_cheque", "=", True),
                ("partner_id.commercial_partner_id", "=", self.partner_id.commercial_partner_id.id),
                ("x4u_pdc_state", "in", ("received", "deposited", "cleared")),
            ]
        else:
            domain = [("journal_id", "=", self.journal_id.id), ("x4u_pdc_state", "in", ("issued", "cleared"))]
        twin = self.search(
            [("id", "!=", self.id), ("x4u_cheque_number", "=", self.x4u_cheque_number), *domain], limit=1
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
        """The bank refused the cheque, and the invoice or bill is open again.

        Not yet with the bank (issued to a vendor, in hand from a customer): the payment is cancelled.
        Deposited: the deposit entry stays as the bank booked it, and Dr Customer / Cr Bank brings
        the debt back (spec §12 K5)."""
        for pay in self:
            if pay.x4u_pdc_state not in OPEN_PDC_STATES:
                raise UserError(_("Only a cheque that the bank has not paid can bounce."))
            documents = pay.reconciled_bill_ids | pay.reconciled_invoice_ids
            if pay.x4u_pdc_state == "deposited":
                pay._x4u_bounce_deposited()
            else:
                # Out of a deposit that is not validated yet.
                pay.move_id.line_ids.filtered("check_deposit_id").check_deposit_id = False
                pay.action_draft()
                pay.action_cancel()
            pay.write({"x4u_pdc_bounced": True, "x4u_pdc_bounce_reason": reason})
            body = _("Cheque %(number)s bounced: %(reason)s", number=pay.x4u_cheque_number, reason=reason)
            pay.message_post(body=body)
            for document in documents:
                document.message_post(body=body)

    def _x4u_bounce_deposited(self):
        self.ensure_one()
        deposit_line = self.x4u_deposit_line_ids.filtered(lambda line: line.parent_state == "posted" and not line.reconciled)
        receivable = self.move_id.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        if len(deposit_line) != 1 or len(receivable) != 1:
            raise UserError(_("Cheque %s is not on one open deposit line.", self.x4u_cheque_number))
        deposit = self.env["account.check.deposit"].search([("move_id", "=", deposit_line.move_id.id)], limit=1)
        label = _("Cheque %(number)s bounced - %(payment)s", number=self.x4u_cheque_number, payment=self.name)
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": (deposit.bank_journal_id or deposit_line.journal_id).id,
                "date": fields.Date.context_today(self),
                "ref": label,
                "line_ids": [
                    Command.create(
                        {
                            "name": label,
                            "account_id": line.account_id.id,
                            "partner_id": line.partner_id.id or self.partner_id.id,
                            "currency_id": line.currency_id.id,
                            "amount_currency": -line.amount_currency,
                            "balance": -line.balance,
                        }
                    )
                    for line in receivable + deposit_line
                ],
            }
        )
        move.action_post()
        # The invoice is open again; the payment's receivable line now meets the bounce's.
        receivable.remove_move_reconcile()
        for line in receivable + deposit_line:
            (line + move.line_ids.filtered(lambda new, old=line: new.account_id == old.account_id)).reconcile()
        self.x4u_pdc_bounce_move_id = move
