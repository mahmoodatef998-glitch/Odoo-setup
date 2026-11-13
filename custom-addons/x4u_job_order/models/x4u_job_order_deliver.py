from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class X4uJobOrderDeliver(models.TransientModel):
    """Deliver Materials: the Storekeeper sends the parts of one Job Order to the factory
    from inside the order (spec v0.4 V3). Behind it, the Pick Components transfer is
    validated; what is not delivered now stays on a backorder for the same order.

    Spec v0.8: the parts are free in stock (F2), each engine goes with the serial the Storekeeper
    picks from a list (N3), and each alternator with its serial when it has one (v0.8.1 N4).
    Engines and alternators have one line per unit, so each line has its own list."""

    _name = "x4u.job.order.deliver"
    _description = "Deliver Materials"

    production_id = fields.Many2one("mrp.production", string="Job Order", required=True, readonly=True)
    line_ids = fields.One2many("x4u.job.order.deliver.line", "wizard_id", string="Parts")

    @api.model
    def _x4u_line_values(self, moves):
        """One line per engine and per alternator, one line per move for the other parts."""
        values = []
        for move in moves:
            if move.has_tracking == "serial" or move.x4u_role == "alternator":
                free = move._x4u_deliverable_qty()
                for unit in range(int(move.product_uom_qty)):
                    # An engine is not proposed: the Storekeeper picks its serial (N3).
                    quantity = 0.0 if move.has_tracking == "serial" else float(unit < free)
                    values.append({"move_id": move.id, "needed": 1.0, "quantity": quantity})
            else:
                values.append({"move_id": move.id, "needed": move.product_uom_qty, "quantity": move._x4u_deliverable_qty()})
        return values

    def action_confirm(self):
        self.ensure_one()
        for line in self.line_ids.filtered(lambda l: l.tracking == "serial"):
            line.quantity = 1.0 if line.lot_id else 0.0
        problems = []
        lots = self.line_ids.lot_id
        if len(lots) < len(self.line_ids.filtered("lot_id")):
            problems.append(_("- The same engine serial is chosen twice."))
        alternators = self.line_ids.alternator_serial_id
        if len(alternators) < len(self.line_ids.filtered("alternator_serial_id")):
            problems.append(_("- The same alternator serial is chosen twice."))
        by_move = defaultdict(lambda: self.env["x4u.job.order.deliver.line"])
        for line in self.line_ids:
            by_move[line.move_id] |= line
        for move, lines in by_move.items():
            rounding = move.product_uom.rounding
            total = sum(lines.mapped("quantity"))
            part = move.product_id.display_name
            if any(float_compare(q, 0, precision_rounding=rounding) < 0 for q in lines.mapped("quantity")) or float_compare(
                total, move.product_uom_qty, precision_rounding=rounding
            ) > 0:
                problems.append(_("- %(part)s: 0 to %(needed)g", part=part, needed=move.product_uom_qty))
            elif float_compare(total, move._x4u_deliverable_qty(), precision_rounding=rounding) > 0:
                problems.append(_("- %(part)s: only %(there)g in stock", part=part, there=move._x4u_deliverable_qty()))
            missing = lines.lot_id - lines.available_lot_ids
            if missing:
                problems.append(_("- %(part)s: %(lots)s not in stock", part=part, lots=", ".join(missing.mapped("name"))))
            not_free = lines.alternator_serial_id.filtered(lambda s, p=move.product_id: s.state != "in_stock" or s.product_id != p)
            if not_free:
                problems.append(_("- %(part)s: %(serials)s not in stock", part=part, serials=", ".join(not_free.mapped("name"))))
            idle = lines.filtered(lambda l: l.alternator_serial_id and float_is_zero(l.quantity, precision_rounding=rounding))
            if idle:
                problems.append(_("- %(part)s: deliver the alternator of serial %(serials)s", part=part, serials=", ".join(idle.alternator_serial_id.mapped("name"))))
        if problems:
            raise UserError(_("Check these parts:\n%s", "\n".join(problems)))
        to_deliver = self.line_ids.filtered(
            lambda line: not float_is_zero(line.quantity, precision_rounding=line.move_id.product_uom.rounding)
        )
        if not to_deliver:
            raise UserError(_("Enter the quantity to deliver for at least one part, and pick the serial of each engine."))
        for move in to_deliver.move_id:
            to_deliver.filtered(lambda l, m=move: l.move_id == m)._x4u_take_from_stock()
        # A part not delivered now waits on a backorder of the same Job Order.
        (self.line_ids.move_id - to_deliver.move_id).picked = False
        to_deliver.move_id.picking_id.with_context(skip_backorder=True).button_validate()
        # The engine goes on the generator card when Pick Components is done (stock.picking);
        # the alternator serials here.
        production = self.production_id.sudo()
        fitted = to_deliver.alternator_serial_id.sudo()
        if fitted:
            fitted.write({"state": "fitted", "production_id": production.id})
            card = production.lot_producing_id.x4u_generator_id
            if card:
                card.write({"alternator_serial": " / ".join(fitted.mapped("name"))})
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
    needed = fields.Float(string="Needed", digits="Product Unit of Measure", readonly=True)
    on_hand = fields.Float(compute="_compute_stock", string="On Hand", digits="Product Unit of Measure")
    quantity = fields.Float(string="To Deliver", digits="Product Unit of Measure")
    available_lot_ids = fields.Many2many("stock.lot", compute="_compute_stock", string="Engines in Stock")
    lot_id = fields.Many2one("stock.lot", string="Engine Serial")
    available_alternator_ids = fields.Many2many(
        "x4u.alternator.serial", compute="_compute_stock", string="Alternators in Stock"
    )
    alternator_serial_id = fields.Many2one(
        "x4u.alternator.serial", string="Alternator Serial", help="Optional: the Job Order goes on without it (spec v0.8.1 N4)."
    )

    @api.depends("move_id")
    def _compute_stock(self):
        Quant = self.env["stock.quant"].sudo()
        Serial = self.env["x4u.alternator.serial"].sudo()
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
            line.available_alternator_ids = (
                Serial.search([("product_id", "=", move.product_id.id), ("state", "=", "in_stock")])
                if move.x4u_role == "alternator"
                else Serial
            )

    @api.onchange("lot_id")
    def _onchange_lot_id(self):
        if self.tracking == "serial":
            self.quantity = 1.0 if self.lot_id else 0.0

    @api.onchange("alternator_serial_id")
    def _onchange_alternator_serial_id(self):
        if self.alternator_serial_id:
            self.quantity = 1.0

    def _x4u_take_from_stock(self):
        """Put the quantity on the Pick Components move of these lines: the serials chosen for the
        engines, what is in stock for the other parts (spec v0.8 F2, N3)."""
        move = self.move_id
        move.ensure_one()
        if move.has_tracking == "serial":
            Quant = self.env["stock.quant"].sudo()
            move.move_line_ids.unlink()
            commands = []
            for lot in self.lot_id:
                quant = Quant._gather(move.product_id, move.location_id, lot_id=lot, strict=False).filtered(
                    lambda q: q.quantity > q.reserved_quantity
                )[:1]
                commands.append(Command.create(move._prepare_move_line_vals(quantity=1, reserved_quant=quant)))
            move.move_line_ids = commands
        else:
            move.quantity = sum(self.mapped("quantity"))
        move.picked = True
