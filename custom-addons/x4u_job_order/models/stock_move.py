from odoo import api, fields, models

ROLE_CATEGORIES = (
    ("engine", "x4u_setup_base.categ_engines"),
    ("alternator", "x4u_setup_base.categ_alternators"),
    ("body", "x4u_setup_base.categ_bodies"),
)


class StockMove(models.Model):
    _inherit = "stock.move"

    x4u_role = fields.Selection(
        [("engine", "Engine"), ("alternator", "Alternator"), ("body", "Body")],
        string="Part",
        compute="_compute_x4u_role",
    )
    x4u_part_status = fields.Selection(
        [
            ("requested", "Requested"),
            ("rfq", "RFQ"),
            ("ordered", "Ordered"),
            ("from_stock", "From Stock"),
            ("received", "Received"),
            ("delivered", "Delivered to factory"),
        ],
        string="Part Status",
        compute="_compute_x4u_part",
    )
    x4u_purchase_id = fields.Many2one("purchase.order", string="Purchase Order", compute="_compute_x4u_part")
    x4u_vendor_id = fields.Many2one("res.partner", string="Vendor", compute="_compute_x4u_part")
    x4u_expected_date = fields.Datetime(string="Expected", compute="_compute_x4u_part")
    x4u_stock_on_hand = fields.Float(
        string="On Hand",
        compute="_compute_x4u_stock",
        digits="Product Unit of Measure",
        help="What the warehouse stock (WH/Stock) holds of this part now.",
    )
    x4u_stock_free = fields.Float(
        string="Free to Use",
        compute="_compute_x4u_stock",
        digits="Product Unit of Measure",
        help="On hand minus what is already reserved for other transfers and Job Orders.",
    )

    def _action_assign(self, force_qty=False):
        res = super()._action_assign(force_qty=force_qty)
        # A part reserved later (receipt, Check Availability) makes its Job Order Parts Ready.
        self.env["mrp.production"].sudo()._x4u_from_moves(self)._x4u_check_parts_ready()
        return res

    def _x4u_deliverable_qty(self):
        """What can go to the factory now for this Pick Components move: what is reserved
        for it, plus what is free in stock, up to what it still needs (spec v0.4 V3)."""
        self.ensure_one()
        free = self.product_id.sudo().with_context(location=self.location_id.id).free_qty
        free = self.product_id.uom_id._compute_quantity(max(free, 0.0), self.product_uom)
        return min(self.product_uom_qty, self.quantity + free)

    def _prepare_procurement_values(self):
        values = super()._prepare_procurement_values()
        if not values.get("move_dest_ids"):
            # Odoo 18 never chains "take from stock, else order" moves (False here),
            # and OCA purchase_request expects a recordset.
            values["move_dest_ids"] = self._x4u_job_order_chain()
        return values

    def _x4u_job_order_chain(self):
        """Chain a Job Order part to what is bought for it, so its request, PO and
        receipt can be followed (spec §5). Only when nothing is in stock: a part
        partly taken from stock keeps Odoo's default (reserve from stock)."""
        self.ensure_one()
        if (
            self.rule_id.procure_method == "mts_else_mto"
            and self.move_dest_ids.raw_material_production_id.filtered("x4u_is_job_order")
            and self.product_id.with_context(location=self.location_id.id).free_qty <= 0
        ):
            return self
        return self.browse()

    @api.depends("product_id.categ_id")
    def _compute_x4u_role(self):
        roots = [(role, self.env.ref(xmlid, raise_if_not_found=False)) for role, xmlid in ROLE_CATEGORIES]
        for move in self:
            path = move.product_id.categ_id.parent_path or ""
            move.x4u_role = next((role for role, categ in roots if categ and path.startswith(categ.parent_path)), False)

    @api.depends("product_id", "product_uom", "raw_material_production_id.picking_type_id")
    def _compute_x4u_stock(self):
        """What the warehouse holds of each part, seen while the quantities are entered
        (2026-10-27). Read with sudo: Quality and Purchasing read Job Orders without
        stock rights, and these are numbers only."""
        for move in self:
            warehouse = move.raw_material_production_id.picking_type_id.warehouse_id or move.warehouse_id
            location = warehouse.lot_stock_id
            on_hand = free = 0.0
            if location and move.product_id.is_storable:
                product = move.product_id.sudo().with_context(location=location.id)
                unit = move.product_uom or product.uom_id
                on_hand = product.uom_id._compute_quantity(product.qty_available, unit)
                free = product.uom_id._compute_quantity(product.free_qty, unit)
            move.x4u_stock_on_hand = on_hand
            move.x4u_stock_free = free

    def _compute_x4u_part(self):
        PurchaseLine = self.env["purchase.order.line"].sudo()
        RequestLine = self.env["purchase.request.line"].sudo()
        for move in self:
            picks = move.move_orig_ids.filtered(lambda m: m.state != "cancel")
            source = picks or move
            receipts = source.move_orig_ids.filtered(lambda m: m.state != "cancel")
            # Once the PO is confirmed, Odoo moves the link from the PO line to its receipt.
            # sudo first: people who only read the Job Order (Quality) can't read purchases.
            po_lines = (
                PurchaseLine.search([("move_dest_ids", "in", source.ids)]) | receipts.sudo().purchase_line_id
            ).filtered(lambda line: line.state != "cancel")
            status = False
            if all(m.state == "done" for m in source) and source:
                status = "delivered"
            elif receipts and all(m.state == "done" for m in receipts):
                status = "received"
            elif po_lines:
                status = "ordered" if any(line.order_id.state in ("purchase", "done") for line in po_lines) else "rfq"
            elif RequestLine.search_count([("move_dest_ids", "in", source.ids)]):
                status = "requested"
            elif all(m.state in ("assigned", "partially_available") for m in source):
                status = "from_stock"
            move.x4u_part_status = status
            move.x4u_purchase_id = po_lines[:1].order_id
            move.x4u_vendor_id = po_lines[:1].partner_id
            move.x4u_expected_date = po_lines[:1].date_planned
