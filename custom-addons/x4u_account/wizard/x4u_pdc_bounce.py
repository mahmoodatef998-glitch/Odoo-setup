from odoo import fields, models


class X4uPdcBounce(models.TransientModel):
    _name = "x4u.pdc.bounce"
    _description = "Cheque Bounced"

    payment_id = fields.Many2one("account.payment", required=True, readonly=True)
    reason = fields.Text(required=True, help="What the bank said, e.g. insufficient funds, signature mismatch.")

    def action_confirm(self):
        self.payment_id._x4u_pdc_bounce(self.reason)
        return {"type": "ir.actions.act_window_close"}
