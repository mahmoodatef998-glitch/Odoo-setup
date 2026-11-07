from odoo import api, models

PDC = "x4u_pdc"


class AccountPaymentMethod(models.Model):
    _inherit = "account.payment.method"

    @api.model
    def _get_payment_method_information(self):
        """PDC Cheque: on every bank journal, for payments to vendors (spec §3)."""
        res = super()._get_payment_method_information()
        res[PDC] = {"mode": "multi", "type": ("bank",)}
        return res
