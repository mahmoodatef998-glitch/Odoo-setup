from odoo import _, api, fields, models


class StockLot(models.Model):
    _inherit = "stock.lot"

    x4u_generator_ids = fields.One2many(
        "x4u.generator", "lot_id", string="Generator Cards"
    )
    x4u_generator_id = fields.Many2one(
        "x4u.generator",
        string="Generator Card",
        compute="_compute_x4u_generator_id",
    )
    x4u_is_generator = fields.Boolean(related="product_id.x4u_is_generator")

    @api.depends("x4u_generator_ids")
    def _compute_x4u_generator_id(self):
        for lot in self:
            lot.x4u_generator_id = lot.x4u_generator_ids[:1]

    @api.model_create_multi
    def create(self, vals_list):
        lots = super().create(vals_list)
        lots._x4u_create_generator_cards()
        return lots

    def _x4u_create_generator_cards(self):
        """Create the missing Generator Cards of generator serials (spec R2)."""
        lots = self.filtered("product_id.x4u_is_generator")
        Generator = self.env["x4u.generator"].sudo().with_context(active_test=False)
        lots -= Generator.search([("lot_id", "in", lots.ids)]).lot_id
        cards = Generator.create([{"lot_id": lot.id} for lot in lots])
        self.invalidate_recordset(["x4u_generator_ids", "x4u_generator_id"])
        return cards

    def action_x4u_create_generator_card(self):
        self._x4u_create_generator_cards()
        return self.action_x4u_open_generator_card()

    def action_x4u_open_generator_card(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Generator Card"),
            "res_model": "x4u.generator",
            "res_id": self.x4u_generator_id.id,
            "view_mode": "form",
        }
