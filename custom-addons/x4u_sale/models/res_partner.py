from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # §6 S4: the Orders tab. Salespeople see their own orders (record rules), Accounting all.
    x4u_sale_order_ids = fields.Many2many(
        "sale.order", string="Confirmed Orders", compute="_compute_x4u_sale_order_ids"
    )

    # What the user may see: one value per user, not one cached for all of them.
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_x4u_sale_order_ids(self):
        Order = self.env["sale.order"]
        allowed = Order.has_access("read")
        for partner in self:
            if not allowed or not partner.id:
                partner.x4u_sale_order_ids = Order
                continue
            partner.x4u_sale_order_ids = Order.search(
                [("partner_id", "child_of", partner.commercial_partner_id.id), ("state", "=", "sale")]
            )
