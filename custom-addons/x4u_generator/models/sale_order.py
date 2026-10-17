from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    x4u_generator_count = fields.Integer(
        string="Generators",
        compute="_compute_x4u_generator_count",
        groups="stock.group_stock_user,sales_team.group_sale_salesman",
    )

    def _compute_x4u_generator_count(self):
        counts = dict(
            self.env["x4u.generator"]._read_group(
                [("sale_order_id", "in", self._origin.ids)],
                ["sale_order_id"],
                ["__count"],
            )
        )
        for order in self:
            order.x4u_generator_count = counts.get(order._origin, 0)

    def action_x4u_view_generators(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "x4u_generator.action_x4u_generator"
        )
        action["domain"] = [("sale_order_id", "=", self.id)]
        action["context"] = {"create": False}
        return action
