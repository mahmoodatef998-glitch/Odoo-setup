from odoo import api, fields, models

from ..models.account_payment_method import PDC


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    x4u_cheque_number = fields.Char(string="Cheque Number")
    x4u_cheque_date = fields.Date(string="Cheque Date")
    x4u_is_cheque = fields.Boolean(compute="_compute_x4u_is_cheque")

    @api.depends("payment_method_line_id", "journal_id", "payment_type")
    def _compute_x4u_is_cheque(self):
        for wizard in self:
            wizard.x4u_is_cheque = wizard.payment_method_line_id.code == PDC or bool(
                wizard.payment_type == "inbound"
                and wizard.journal_id
                and wizard.journal_id == wizard.company_id.x4u_pdc_received_journal_id
            )

    def _x4u_cheque_vals(self, vals):
        method_line = self.env["account.payment.method.line"].browse(vals.get("payment_method_line_id"))
        journal = self.env["account.journal"].browse(vals.get("journal_id"))
        received = vals.get("payment_type") == "inbound" and journal and journal == journal.company_id.x4u_pdc_received_journal_id
        if method_line.code == PDC or received:
            vals.update({"x4u_cheque_number": self.x4u_cheque_number, "x4u_cheque_date": self.x4u_cheque_date})
        return vals

    def _create_payment_vals_from_wizard(self, batch_result):
        return self._x4u_cheque_vals(super()._create_payment_vals_from_wizard(batch_result))

    def _create_payment_vals_from_batch(self, batch_result):
        return self._x4u_cheque_vals(super()._create_payment_vals_from_batch(batch_result))
