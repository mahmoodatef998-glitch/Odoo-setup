from odoo import _, fields, models
from odoo.exceptions import UserError


class X4uReadyReceipt(models.TransientModel):
    """Spec v0.8 N7: a ready generator is received with the serial of the engine inside it, from the
    supplier's papers, and the alternator's and the supplier's own serials when known. They go on
    the Ready Job Order and the generator card."""

    _name = "x4u.ready.receipt"
    _description = "Ready Generator Serials"

    picking_ids = fields.Many2many("stock.picking", string="Receipts", readonly=True)
    line_ids = fields.One2many("x4u.ready.receipt.line", "wizard_id", string="Generators")

    def action_confirm(self):
        self.ensure_one()
        missing = self.line_ids.filtered(lambda line: not (line.engine_serial or "").strip())
        if missing:
            raise UserError(
                _("Write the engine serial of %s: every engine has its serial.", ", ".join(missing.ready_order_id.mapped("name")))
            )
        for line in self.line_ids:
            line.ready_order_id.sudo().write(
                {
                    "engine_serial": line.engine_serial.strip(),
                    "alternator_serial": (line.alternator_serial or "").strip() or False,
                    "supplier_serial": (line.supplier_serial or "").strip() or False,
                }
            )
        res = self.picking_ids.with_context(x4u_ready_serials_done=True).button_validate()
        return res if isinstance(res, dict) else {"type": "ir.actions.act_window_close"}


class X4uReadyReceiptLine(models.TransientModel):
    _name = "x4u.ready.receipt.line"
    _description = "Ready Generator Serials Line"

    wizard_id = fields.Many2one("x4u.ready.receipt", required=True, ondelete="cascade")
    ready_order_id = fields.Many2one("x4u.ready.order", string="Ready Job Order", required=True, readonly=True)
    product_id = fields.Many2one(related="ready_order_id.product_id")
    engine_serial = fields.Char(string="Engine Serial")
    alternator_serial = fields.Char(string="Alternator Serial")
    supplier_serial = fields.Char(string="Supplier Serial No")
