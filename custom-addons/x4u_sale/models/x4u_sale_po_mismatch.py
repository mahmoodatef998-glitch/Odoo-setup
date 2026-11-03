from odoo import fields, models


class X4uSalePoMismatch(models.TransientModel):
    """S5: why the customer PO doesn't match the quotation; the Salesperson gets a to-do."""

    _name = "x4u.sale.po.mismatch"
    _description = "Customer PO Doesn't Match"

    order_id = fields.Many2one("sale.order", string="Sales Order", required=True, readonly=True)
    reason = fields.Text(string="What Doesn't Match", required=True)

    def action_confirm(self):
        self.ensure_one()
        self.order_id._x4u_po_mismatch(self.reason)
        return {"type": "ir.actions.act_window_close"}
