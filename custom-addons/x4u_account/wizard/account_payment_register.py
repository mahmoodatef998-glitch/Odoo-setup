from odoo import fields, models

from ..models.account_payment_method import PDC


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    x4u_cheque_number = fields.Char(string="Cheque Number")
    x4u_cheque_date = fields.Date(string="Cheque Date")

    def _x4u_cheque_vals(self, vals):
        method_line = self.env["account.payment.method.line"].browse(vals.get("payment_method_line_id"))
        if method_line.code == PDC:
            vals.update({"x4u_cheque_number": self.x4u_cheque_number, "x4u_cheque_date": self.x4u_cheque_date})
        return vals

    def _create_payment_vals_from_wizard(self, batch_result):
        return self._x4u_cheque_vals(super()._create_payment_vals_from_wizard(batch_result))

    def _create_payment_vals_from_batch(self, batch_result):
        return self._x4u_cheque_vals(super()._create_payment_vals_from_batch(batch_result))
