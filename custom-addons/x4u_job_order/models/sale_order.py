from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            productions = order.mrp_production_ids.sudo()
            productions._x4u_log("order_opened", document=order, date=order.date_order)
            # Odoo links the sale to the Job Order only after confirming it: fill the card now.
            productions._x4u_fill_generator_card()
        return res
