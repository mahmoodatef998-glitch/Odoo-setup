from odoo import api, fields, models


class X4uJobOrderCkd(models.TransientModel):
    """Use CKD (spec v0.9 C3): the Operation Manager picks the CKD that replaces the engine and the
    alternator of one Job Order, seeing what WH/Stock holds of each."""

    _name = "x4u.job.order.ckd"
    _description = "Use CKD"

    production_id = fields.Many2one("mrp.production", string="Job Order", required=True, readonly=True)
    allowed_product_ids = fields.Many2many("product.product", compute="_compute_allowed_product_ids")
    product_id = fields.Many2one(
        "product.product", string="CKD", required=True, domain="[('id', 'in', allowed_product_ids)]"
    )
    on_hand = fields.Float(string="On Hand", compute="_compute_stock", digits="Product Unit of Measure")
    free_qty = fields.Float(string="Free to Use", compute="_compute_stock", digits="Product Unit of Measure")

    @api.depends("production_id")
    def _compute_allowed_product_ids(self):
        ckd = self.env.ref("x4u_setup_base.categ_ckd", raise_if_not_found=False)
        products = self.env["product.product"]
        if ckd:
            products = products.search([("categ_id", "child_of", ckd.id), ("is_storable", "=", True)])
        for wizard in self:
            wizard.allowed_product_ids = products

    @api.depends("product_id", "production_id")
    def _compute_stock(self):
        for wizard in self:
            location = wizard.production_id.picking_type_id.warehouse_id.lot_stock_id
            product = wizard.product_id.sudo().with_context(location=location.id)
            wizard.on_hand = product.qty_available if wizard.product_id and location else 0.0
            wizard.free_qty = product.free_qty if wizard.product_id and location else 0.0

    def action_confirm(self):
        self.ensure_one()
        self.production_id._x4u_check_switch()
        self.production_id._x4u_switch_parts(self.product_id)
        return {"type": "ir.actions.act_window_close"}
