from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # P10: the Purchase Orders tab on the vendor, for Purchasing and Accounting.
    x4u_purchase_order_ids = fields.Many2many(
        "purchase.order", string="Approved Purchase Orders", compute="_compute_x4u_purchase_order_ids"
    )

    # What the user may see: one value per user, not one cached for all of them.
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_x4u_purchase_order_ids(self):
        Order = self.env["purchase.order"]
        allowed = Order.has_access("read")
        for partner in self:
            if not allowed or not partner.id:
                partner.x4u_purchase_order_ids = Order
                continue
            partner.x4u_purchase_order_ids = Order.search(
                [("partner_id", "child_of", partner.commercial_partner_id.id), ("state", "in", ("purchase", "done"))]
            )
