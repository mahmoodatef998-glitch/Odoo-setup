from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class X4uJobOrderDeliver(models.TransientModel):
    """Deliver Materials: the Storekeeper sends the parts of one Job Order to the factory
    from inside the order (spec v0.4 V3). Behind it, the Pick Components transfer is
    validated; what is not delivered now stays on a backorder for the same order."""

    _name = "x4u.job.order.deliver"
    _description = "Deliver Materials"

    production_id = fields.Many2one("mrp.production", string="Job Order", required=True, readonly=True)
    line_ids = fields.One2many("x4u.job.order.deliver.line", "wizard_id", string="Parts")

    def action_confirm(self):
        self.ensure_one()
        problems = []
        for line in self.line_ids:
            move, rounding = line.move_id, line.move_id.product_uom.rounding
            if float_compare(line.quantity, 0, precision_rounding=rounding) < 0 or float_compare(
                line.quantity, move.product_uom_qty, precision_rounding=rounding
            ) > 0:
                problems.append(_("- %(part)s: 0 to %(needed)g", part=move.product_id.display_name, needed=move.product_uom_qty))
            elif float_compare(line.quantity, move._x4u_deliverable_qty(), precision_rounding=rounding) > 0:
                problems.append(
                    _("- %(part)s: only %(there)g in stock", part=move.product_id.display_name, there=move._x4u_deliverable_qty())
                )
        if problems:
            raise UserError(_("Check these quantities:\n%s", "\n".join(problems)))
        to_deliver = self.line_ids.filtered(
            lambda line: not float_is_zero(line.quantity, precision_rounding=line.move_id.product_uom.rounding)
        )
        if not to_deliver:
            raise UserError(_("Enter the quantity to deliver for at least one part."))
        for line in to_deliver:
            line.move_id.quantity = line.quantity
            line.move_id.picked = True
        # A part not delivered now keeps its reservation and waits on a backorder.
        (self.line_ids - to_deliver).move_id.picked = False
        to_deliver.move_id.picking_id.with_context(skip_backorder=True).button_validate()
        return {"type": "ir.actions.act_window_close"}


class X4uJobOrderDeliverLine(models.TransientModel):
    _name = "x4u.job.order.deliver.line"
    _description = "Deliver Materials Line"

    wizard_id = fields.Many2one("x4u.job.order.deliver", required=True, ondelete="cascade")
    move_id = fields.Many2one("stock.move", required=True, readonly=True)
    x4u_role = fields.Selection(related="move_id.x4u_role")
    product_id = fields.Many2one(related="move_id.product_id")
    product_uom_id = fields.Many2one(related="move_id.product_uom", string="Unit")
    needed = fields.Float(related="move_id.product_uom_qty", string="Needed")
    reserved = fields.Float(related="move_id.quantity", string="Reserved for this order")
    on_hand = fields.Float(compute="_compute_stock", string="On Hand", digits="Product Unit of Measure")
    free = fields.Float(compute="_compute_stock", string="Free to Use", digits="Product Unit of Measure")
    quantity = fields.Float(string="To Deliver", digits="Product Unit of Measure")

    @api.depends("move_id")
    def _compute_stock(self):
        for line in self:
            move = line.move_id
            product = move.product_id.sudo().with_context(location=move.location_id.id)
            line.on_hand = product.uom_id._compute_quantity(product.qty_available, move.product_uom)
            line.free = product.uom_id._compute_quantity(product.free_qty, move.product_uom)
