from odoo import api, fields, models

from .account_payment import OPEN_PDC_STATES


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_invoice_in_payment_state(self):
        """A bill or invoice paid by a cheque the bank has not paid yet is In Payment, not Paid
        (spec §2 P8, §12). Only cheques: other payments keep Odoo Community's behaviour (Paid at once)."""
        state = super()._get_invoice_in_payment_state()
        if state == "paid" and len(self) == 1:
            if any(pay.x4u_pdc_state in OPEN_PDC_STATES for pay in self.sudo()._get_reconciled_payments()):
                return "in_payment"
        return state

    # Odoo's dependencies (account 18.0) plus the cheque status.
    @api.depends(
        "amount_residual", "move_type", "state", "company_id", "reconciled_payment_ids.state",
        "reconciled_payment_ids.x4u_pdc_state",
    )
    def _compute_payment_state(self):
        """A deposited customer cheque is matched in PDC Received, so Odoo says Paid; it stays
        In Payment until the bank clears it (spec §12 K4)."""
        res = super()._compute_payment_state()
        for move in self:
            if move.payment_state == "paid" and move.is_invoice(True) and any(
                pay.x4u_pdc_state in OPEN_PDC_STATES for pay in move.sudo().reconciled_payment_ids
            ):
                move.payment_state = "in_payment"
        return res

    def _post(self, soft=True):
        posted = super()._post(soft)
        # Spec §9 S6: a line delivered before its invoice is settled by Odoo's own cost of sales;
        # one invoiced first is settled here when the delivery has also come.
        posted.filtered(lambda move: move.is_sale_document()).invoice_line_ids.sale_line_ids._x4u_settle_cogs()
        return posted


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    x4u_deposit_payment_id = fields.Many2one(
        "account.payment", string="Deposited Cheque", copy=False, index="btree_not_null", readonly=True,
        help="On a cheque deposit entry: the customer cheque of this bank line (spec §12 K4).",
    )
    x4u_cogs_sale_line_id = fields.Many2one(
        "sale.order.line", string="Cost of Sales For", copy=False, index="btree_not_null", readonly=True,
        help="Cost of sales posted when the delivery came after the invoice (spec §9 S6).",
    )

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
