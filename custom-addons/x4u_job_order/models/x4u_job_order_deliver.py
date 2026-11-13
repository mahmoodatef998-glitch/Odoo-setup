from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class X4uJobOrderDeliver(models.TransientModel):
    """Deliver Materials: the Storekeeper sends the parts of one Job Order to the factory
    from inside the order (spec v0.4 V3). Behind it, the Pick Components transfer is
    validated; what is not delivered now stays on a backorder for the same order.

    Spec v0.8: the parts are free in stock (F2), and each engine goes with the serial the
    Storekeeper picks (N3); the alternator serial is written when known (N4)."""

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
            elif line.tracking == "serial" and len(line.lot_ids) != int(line.quantity):
                problems.append(
                    _(
                        "- %(part)s: choose the serial of each one (%(needed)g to deliver, %(chosen)s chosen)",
                        part=move.product_id.display_name, needed=line.quantity, chosen=len(line.lot_ids),
                    )
                )
            elif line.lot_ids - line.available_lot_ids:
                problems.append(
                    _(
                        "- %(part)s: %(lots)s not in stock",
                        part=move.product_id.display_name, lots=", ".join((line.lot_ids - line.available_lot_ids).mapped("name")),
                    )
                )
        if problems:
            raise UserError(_("Check these parts:\n%s", "\n".join(problems)))
        to_deliver = self.line_ids.filtered(
            lambda line: not float_is_zero(line.quantity, precision_rounding=line.move_id.product_uom.rounding)
        )
        if not to_deliver:
            raise UserError(_("Enter the quantity to deliver for at least one part, and the serial of each engine."))
        for line in to_deliver:
            line._x4u_take_from_stock()
        # A part not delivered now waits on a backorder of the same Job Order.
        (self.line_ids - to_deliver).move_id.picked = False
        to_deliver.move_id.picking_id.with_context(skip_backorder=True).button_validate()
        # The engine goes on the generator card when Pick Components is done (stock.picking).
        production = self.production_id.sudo()
        alternator = " / ".join(
            serial.strip() for serial in to_deliver.filtered(lambda line: line.x4u_role == "alternator").mapped("alternator_serial")
            if serial and serial.strip()
        )
        card = production.lot_producing_id.x4u_generator_id
        if alternator and card:
            card.write({"alternator_serial": alternator})
        return {"type": "ir.actions.act_window_close"}


class X4uJobOrderDeliverLine(models.TransientModel):
    _name = "x4u.job.order.deliver.line"
    _description = "Deliver Materials Line"

    wizard_id = fields.Many2one("x4u.job.order.deliver", required=True, ondelete="cascade")
    move_id = fields.Many2one("stock.move", required=True, readonly=True)
    x4u_role = fields.Selection(related="move_id.x4u_role")
    product_id = fields.Many2one(related="move_id.product_id")
    product_uom_id = fields.Many2one(related="move_id.product_uom", string="Unit")
    tracking = fields.Selection(related="move_id.has_tracking")
    needed = fields.Float(related="move_id.product_uom_qty", string="Needed")
    on_hand = fields.Float(compute="_compute_stock", string="On Hand", digits="Product Unit of Measure")
    quantity = fields.Float(string="To Deliver", digits="Product Unit of Measure")
    available_lot_ids = fields.Many2many("stock.lot", compute="_compute_stock", string="Serials in Stock")
    lot_ids = fields.Many2many("stock.lot", string="Engine Serial")
    alternator_serial = fields.Char(string="Alternator Serial", help="Optional: the Job Order goes on without it (spec v0.8 N4).")

    @api.depends("move_id")
    def _compute_stock(self):
        Quant = self.env["stock.quant"].sudo()
        for line in self:
            move = line.move_id
            product = move.product_id.sudo().with_context(location=move.location_id.id)
            line.on_hand = product.uom_id._compute_quantity(product.qty_available, move.product_uom)
            lots = self.env["stock.lot"]
            if move.has_tracking == "serial":
                quants = Quant.search(
                    [
                        ("product_id", "=", move.product_id.id),
                        ("location_id", "child_of", move.location_id.id),
                        ("lot_id", "!=", False),
                        ("quantity", ">", 0),
                    ]
                )
                lots = quants.filtered(lambda q: q.quantity > q.reserved_quantity).lot_id
            line.available_lot_ids = lots

    @api.onchange("lot_ids")
    def _onchange_lot_ids(self):
        if self.tracking == "serial":
            self.quantity = len(self.lot_ids)

    def _x4u_take_from_stock(self):
        """Put the quantity on the Pick Components move: the serials chosen for an engine, what is
        in stock for the other parts (spec v0.8 F2, N3)."""
        self.ensure_one()
        move = self.move_id
        if self.tracking == "serial":
            Quant = self.env["stock.quant"].sudo()
            move.move_line_ids.unlink()
            commands = []
            for lot in self.lot_ids:
                quant = Quant._gather(move.product_id, move.location_id, lot_id=lot, strict=False).filtered(
                    lambda q: q.quantity > q.reserved_quantity
                )[:1]
                commands.append(Command.create(move._prepare_move_line_vals(quantity=1, reserved_quant=quant)))
            move.move_line_ids = commands
        else:
            move.quantity = self.quantity
        move.picked = True
