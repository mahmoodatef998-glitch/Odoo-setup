from odoo import api, models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_invoice_in_payment_state(self):
        """A bill paid by a PDC cheque the bank has not paid yet is In Payment, not Paid (spec §2 P8).
        Only PDC: other payments keep Odoo Community's behaviour (Paid at once)."""
        state = super()._get_invoice_in_payment_state()
        if state == "paid" and len(self) == 1:
            if any(pay.x4u_pdc_state == "issued" for pay in self.sudo()._get_reconciled_payments()):
                return "in_payment"
        return state


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model_create_multi
    def create(self, vals_list):
        """Spec §10: a bill line of a landed cost service is a landed cost line however it is made
        (from a PO, an import, code), not only when the product is picked on the screen."""
        Product = self.env["product.product"]
        for vals in vals_list:
            if "is_landed_costs_line" not in vals and vals.get("product_id"):
                product = Product.browse(vals["product_id"])
                if product.landed_cost_ok and product.type == "service":
                    vals["is_landed_costs_line"] = True
        return super().create(vals_list)
