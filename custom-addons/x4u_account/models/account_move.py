from odoo import _, api, fields, models
from odoo.exceptions import UserError

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

    def _stock_account_prepare_anglo_saxon_out_lines_vals(self):
        """Spec §20 P2: the cost of sales is posted by the delivery (Dr Cost of Sales / Cr Inventory),
        so the stock output account is the cost of sales itself. Odoo would still add Dr and Cr Cost
        of Sales on the invoice, the same amount on the same account: they are left out."""
        vals_list = super()._stock_account_prepare_anglo_saxon_out_lines_vals()
        accounts = {}
        for vals in vals_list:
            accounts.setdefault(vals.get("cogs_origin_id"), set()).add(vals.get("account_id"))
        return [vals for vals in vals_list if len(accounts[vals.get("cogs_origin_id")]) > 1]

    def _x4u_check_trn(self):
        """Spec §21 V2: an invoice, bill or credit note of a UAE company to a VAT registered contact is
        confirmed only with its TRN (FTA: the recipient's TRN is on the tax invoice)."""
        missing = self.filtered(
            lambda move: move.is_invoice()
            and move.company_id.account_fiscal_country_id.code == "AE"
            and move.commercial_partner_id.x4u_vat_registered
            and not move.commercial_partner_id.vat
        )
        if missing:
            raise UserError(
                _(
                    "%(partners)s is VAT registered but has no TRN. Add the TRN on the contact before confirming %(moves)s.",
                    partners=", ".join(sorted(set(missing.commercial_partner_id.mapped("display_name")))),
                    moves=", ".join(missing.mapped("display_name")),
                )
            )

    def _post(self, soft=True):
        self._x4u_check_trn()
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
