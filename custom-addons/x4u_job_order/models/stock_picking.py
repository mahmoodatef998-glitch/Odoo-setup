from odoo import Command, _, models
from odoo.exceptions import UserError

from .x4u_alternator_serial import split_serials


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        if not self.env.context.get("x4u_invoice_delivery"):
            self._x4u_check_paid_delivery()
        unpaid = self._x4u_unpaid_generator_sales()
        res = super()._action_done()
        self._x4u_log_job_orders()
        self._x4u_log_delivered_before_payment(unpaid)
        return res

    def _x4u_check_paid_delivery(self):
        """Spec v0.13 L1: paid before delivery, the goods delivered before the tax invoice stay
        within what was paid on the PI, however they are delivered."""
        for order in self.sudo().sale_id:
            if not order._x4u_delivery_within_paid():
                continue
            moves = self.sudo().move_ids.filtered(
                lambda m, o=order: m.picking_id.sale_id == o
                and m.picking_id.location_dest_id.usage == "customer"
                and m.picked
                and m.state not in ("done", "cancel")
                and m.sale_line_id
            )
            if not moves:
                continue
            value = order._x4u_delivered_value() + sum(
                order._x4u_unit_total(move.sale_line_id) * move.product_uom._compute_quantity(move.quantity, move.sale_line_id.product_uom)
                for move in moves
            )
            if order.currency_id.compare_amounts(value, order._x4u_amount_received()) > 0:
                raise UserError(order._x4u_over_paid_message(value))

    # ------------------------------------------------------------------
    # Delivered before the final invoice is paid: allowed, written on the order
    # (x4u_sale spec §6 B10, user 2026-10-27)
    # ------------------------------------------------------------------
    def _x4u_unpaid_generator_sales(self):
        """Orders paid before delivery, final invoice not paid, with a generator in these deliveries."""
        orders = self.env["sale.order"]
        for picking in self.sudo():
            order = picking.sale_id
            if (
                order.x4u_pay_before_delivery
                and picking.picking_type_code == "outgoing"
                and picking.location_dest_id.usage == "customer"
                and any(move.product_id.x4u_is_generator for move in picking.move_ids)
                and not order.x4u_final_invoice_paid
            ):
                orders |= order
        return orders

    def _x4u_log_delivered_before_payment(self, orders):
        for order in orders:
            pickings = self.sudo().filtered(lambda p, o=order: p.sale_id == o and p.state == "done")
            if pickings:
                order.sudo().message_post(
                    body=_(
                        "Delivered before the final invoice was paid, by %(user)s: %(pickings)s",
                        user=self.env.user.name,
                        pickings=", ".join(pickings.mapped("name")),
                    )
                )

    def _x4u_log_job_orders(self):
        """Receipts, Pick Components and customer deliveries of Job Orders."""
        Production = self.env["mrp.production"].sudo()
        for picking in self.filtered(lambda p: p.state == "done"):
            moves = picking.move_ids.filtered(lambda m: m.state == "done")
            warehouse = picking.picking_type_id.warehouse_id
            if picking.picking_type_code == "incoming":
                # Parts Ready follows the stock (spec v0.8 F4), see stock.move._action_done.
                for move in moves:
                    productions = Production._x4u_from_moves(move.move_dest_ids)
                    productions._x4u_log("part_received", document=picking, detail=move.product_id.display_name)
            elif warehouse and picking.picking_type_id == warehouse.pbm_type_id:
                # Material Delivered once every part is delivered; a part delivered alone waits.
                for production in Production._x4u_from_moves(moves.move_dest_ids):
                    if production.product_qty == 1:
                        # Spec v0.8 N5 / v0.10 B3: the card of a one-generator Job Order gets its engine
                        # (or CKD) and its body now, by their serials.
                        production._x4u_card_parts(
                            moves.filtered(lambda m, p=production: m.move_dest_ids.raw_material_production_id == p)
                        )
                    if production.x4u_job_state not in ("waiting_parts", "parts_ready"):
                        continue
                    if all(move.state == "done" for move in production._x4u_component_moves()):
                        production._x4u_set_state("material_delivered")
                        production._x4u_log("material_delivered", document=picking)
                        production._x4u_notify("operation", _("Finish Job Order %s", production.name))
            lots = picking.move_line_ids.filtered(
                lambda ml: ml.lot_id and ml.location_dest_id.usage == "customer" and ml.location_id.usage != "customer"
            ).lot_id
            if lots:
                productions = Production.search([("lot_producing_id", "in", lots.ids), ("x4u_is_job_order", "=", True)])
                productions._x4u_set_state("delivered")
                productions._x4u_log("delivered", document=picking)
                ready = self.env["x4u.ready.order"].sudo().search([("lot_id", "in", lots.ids), ("state", "=", "in_stock")])
                ready.write({"state": "delivered"})
                for order in ready:
                    order.message_post(body=_("Delivered to the customer in %s.", picking.name))
            if picking.picking_type_code == "incoming":
                received = moves.filtered(lambda m: m.product_id.x4u_is_generator).move_line_ids.lot_id
                names = received.mapped("name")
                orders = self.env["x4u.ready.order"].sudo().search(
                    ["|", ("name", "in", names), ("engine_serial", "in", names), ("state", "=", "waiting")]
                )
                orders._x4u_received(received, picking)

    def button_validate(self):
        self._x4u_check_receipt_serials()
        self._x4u_ready_serials()
        if not self.env.context.get("x4u_ready_serials_done"):
            orders = self._x4u_ready_orders_received().filtered(lambda order: not order.engine_serial)
            if orders:
                return self._x4u_ask_ready_serials(orders)
        self._x4u_ready_lot_names()
        return super().button_validate()

    def _x4u_check_receipt_serials(self):
        """Spec v0.8 N2: every engine, CKD or canopy received has its serial, written in Serials."""
        missing = []
        for move in self.filtered(lambda p: p.picking_type_code == "incoming").move_ids:
            if move.state in ("done", "cancel") or move.has_tracking != "serial" or move.x4u_role not in ("engine", "ckd", "body"):
                continue
            if not move.quantity:
                continue
            written = len(move.move_line_ids.filtered(lambda line: line.lot_id or line.lot_name))
            if written < len(move.move_line_ids) or not written:
                missing.append(
                    _(
                        "- %(part)s: %(qty)g received, %(written)s serials",
                        part=move.product_id.display_name,
                        qty=move.quantity,
                        written=written,
                    )
                )
        # Spec v0.15 B2 (the user, 2026-11-20): an alternator's serial is required at the receipt too.
        for move in self.filtered(lambda p: p.picking_type_code == "incoming").move_ids:
            if move.state in ("done", "cancel") or move.x4u_role != "alternator" or not move.quantity:
                continue
            quantity = move.product_uom._compute_quantity(move.quantity, move.product_id.uom_id)
            written = len(split_serials(move.x4u_alternator_serials))
            if written != int(quantity):
                missing.append(
                    _(
                        "- %(part)s: %(qty)g received, %(written)s serials (Alternator Serials column)",
                        part=move.product_id.display_name,
                        qty=quantity,
                        written=written,
                    )
                )
        if missing:
            raise UserError(
                _(
                    "Write the serial of each unit in the Serials column of the line (E-1001, E-1002...); "
                    "the quantity follows the serials.\n%s",
                    "\n".join(missing),
                )
            )

    def _x4u_ready_lot_names(self):
        """Spec v0.12 J10: a ready generator comes in with the serial of its engine as its serial."""
        Ready = self.env["x4u.ready.order"].sudo()
        lines = self.filtered(lambda p: p.picking_type_code == "incoming" and p.state not in ("done", "cancel")).move_ids.filtered(
            lambda m: m.product_id.x4u_is_generator and m.state not in ("done", "cancel")
        ).move_line_ids.filtered("lot_name")
        for line in lines:
            order = Ready.search([("name", "=", line.lot_name), ("state", "=", "waiting"), ("engine_serial", "!=", False)], limit=1)
            if order:
                line.lot_name = order.engine_serial

    def _x4u_ready_orders_received(self):
        """Ready Job Orders whose generator these receipts bring in (by its RG serial)."""
        lines = self.filtered(lambda p: p.picking_type_code == "incoming" and p.state not in ("done", "cancel")).move_ids.filtered(
            lambda m: m.product_id.x4u_is_generator and m.state not in ("done", "cancel")
        ).move_line_ids
        names = [name for name in lines.mapped("lot_name") + lines.lot_id.mapped("name") if name]
        if not names:
            return self.env["x4u.ready.order"]
        return self.env["x4u.ready.order"].sudo().search(
            ["|", ("name", "in", names), ("engine_serial", "in", names), ("state", "=", "waiting")]
        )

    def _x4u_ask_ready_serials(self, orders):
        """Spec v0.8 N7: the engine serial of each ready generator before it comes in."""
        wizard = self.env["x4u.ready.receipt"].create(
            {
                "picking_ids": [Command.set(self.ids)],
                "line_ids": [Command.create({"ready_order_id": order.id}) for order in orders.sorted("name")],
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Ready Generator Serials"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def _x4u_ready_serials(self):
        """Spec v0.7 G3: a ready generator received for a sale gets its Ready Job Order's number as
        serial (like an assembled one gets its Job Order number), so the Storekeeper types nothing.
        A serial typed by hand stays."""
        Ready = self.env["x4u.ready.order"].sudo()
        for picking in self.filtered(lambda p: p.picking_type_code == "incoming" and p.state not in ("done", "cancel")):
            for move in picking.move_ids.filtered(
                lambda m: m.product_id.x4u_is_generator and m.product_id.tracking == "serial" and m.state not in ("done", "cancel")
            ):
                if any(line.lot_id or line.lot_name for line in move.move_line_ids):
                    continue
                orders = Ready.search(
                    [("sale_line_id", "in", move.move_dest_ids.sale_line_id.ids), ("state", "=", "waiting"), ("lot_id", "=", False)],
                    order="id",
                )
                taken = self.env["stock.move.line"].sudo().search(
                    [("lot_name", "in", orders.mapped("name")), ("state", "not in", ("done", "cancel"))]
                ).mapped("lot_name")
                names = [name for name in orders.mapped("name") if name not in taken]
                quantity = int(move.quantity or move.product_uom_qty)
                names = names[:quantity]
                if not names:
                    continue
                move.move_line_ids.unlink()
                move.write(
                    {
                        "move_line_ids": move._generate_serial_move_line_commands(
                            [{"lot_name": name, "quantity": 1} for name in names]
                        ),
                        "picked": True,
                    }
                )
