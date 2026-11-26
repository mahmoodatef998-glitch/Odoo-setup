from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .stock_move import part_role


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _x4u_job_orders(self):
        # Confirmed POs keep the link on their receipt moves, not on the lines.
        lines = self.order_line
        return self.env["mrp.production"].sudo()._x4u_from_moves(lines.move_dest_ids | lines.move_ids.move_dest_ids)

    def _x4u_log_job_orders(self, event_type):
        for order in self.filtered(lambda o: o.state in ("purchase", "done")):
            order._x4u_job_orders()._x4u_log(
                event_type,
                document=order,
                detail=order.partner_id.display_name,
                date=order.date_approve if event_type == "po_approved" else None,
            )

    def button_approve(self, force=False):
        res = super().button_approve(force=force)
        self._x4u_log_job_orders("po_approved")
        return res

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        # Odoo sets this context when the PO is sent to the vendor by email.
        if self.env.context.get("mark_rfq_as_sent"):
            self._x4u_log_job_orders("po_sent")
        return message


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    # Spec v0.15 B1 (the user, 2026-11-20): what is still to buy of this part to cover the open orders.
    x4u_needed_qty = fields.Float(
        string="Needed for Orders",
        compute="_compute_x4u_needed_qty",
        digits="Product Unit of Measure",
        help="What the open Job Orders still need of this part (not delivered to the factory yet), less what is "
        "in stock and what the other purchase orders bring.",
    )

    @api.depends("product_id", "order_id.state")
    def _compute_x4u_needed_qty(self):
        for line in self:
            product = line.product_id
            if not product or not product.is_storable:
                line.x4u_needed_qty = 0.0
                continue
            need, free, incoming = product._x4u_order_needs(exclude_lines=line._origin)
            line.x4u_needed_qty = max(need - free - incoming, 0.0)

    # The user, 2026-11-26: a full CKD bought on the PO - pick the engine, tick CKD, pick the
    # alternator; on save the line becomes the CKD of that pair (its card made the first time),
    # received with the engine's serial.
    x4u_is_engine = fields.Boolean(compute="_compute_x4u_is_engine")
    x4u_ckd = fields.Boolean(
        string="CKD", copy=False,
        help="Bought as a full CKD: this engine with the alternator chosen, one product with the engine's serial.",
    )
    x4u_ckd_alternator_id = fields.Many2one(
        "product.product", string="CKD Alternator", copy=False,
        domain=lambda self: [("categ_id", "child_of", self.env.ref("x4u_setup_base.categ_alternators").id)],
        help="The alternator coupled to the engine in this CKD.",
    )

    x4u_ckd_engine_id = fields.Many2one("product.product", string="CKD Engine", copy=False, readonly=True)

    @api.depends("product_id")
    def _compute_x4u_is_engine(self):
        for line in self:
            line.x4u_is_engine = bool(line.product_id) and part_role(self.env, line.product_id) == "engine"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for order in lines.order_id:
            order_lines = lines.filtered(lambda line, o=order: line.order_id == o)
            productions = self.env["mrp.production"].sudo()._x4u_from_moves(order_lines.move_dest_ids)
            productions._x4u_log("rfq_created", document=order, detail=order.partner_id.display_name)
        lines._x4u_make_ckd()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if {"x4u_ckd", "x4u_ckd_alternator_id", "product_id"} & set(vals):
            self._x4u_make_ckd()
        return res

    def _x4u_make_ckd(self):
        """An engine line ticked CKD with its alternator becomes the CKD of the pair, at its price;
        another alternator makes it that pair's CKD, and unticking CKD gives the engine back."""
        for line in self.filtered(lambda l: l.x4u_is_engine or l.x4u_ckd_engine_id):
            engine = line.product_id if line.x4u_is_engine else line.x4u_ckd_engine_id
            if line.x4u_ckd and line.x4u_ckd_alternator_id:
                target = self.env["product.product"]._x4u_ckd_for(engine, line.x4u_ckd_alternator_id)
            elif not line.x4u_ckd:
                target = engine
            else:
                continue
            if line.product_id == target:
                continue
            if line.order_id.state not in ("draft", "sent", "to approve"):
                raise UserError(_("%s is confirmed: the CKD is chosen before the order is confirmed.", line.order_id.name))
            if line.move_dest_ids:
                raise UserError(
                    _(
                        "%s is bought for a Job Order: tick Built from CKD on the generator model, or Use CKD on the "
                        "Job Order, so its material request asks for the CKD.",
                        engine.display_name,
                    )
                )
            price = line.price_unit
            line.write({"product_id": target.id, "x4u_ckd_engine_id": engine.id if target != engine else False})
            line.write({"price_unit": price, "name": target.with_context(lang=line.order_id.partner_id.lang).display_name})
