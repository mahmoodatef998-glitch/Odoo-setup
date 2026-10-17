from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    x4u_generator_count = fields.Integer(
        string="Generators",
        compute="_compute_x4u_generator_count",
        groups="stock.group_stock_user,sales_team.group_sale_salesman",
    )

    def _compute_x4u_generator_count(self):
        # Cards store the commercial partner as customer (spec R4).
        commercial_partners = self._origin.commercial_partner_id
        counts = dict(
            self.env["x4u.generator"]._read_group(
                [("customer_id", "in", commercial_partners.ids)],
                ["customer_id"],
                ["__count"],
            )
        )
        for partner in self:
            partner.x4u_generator_count = counts.get(
                partner._origin.commercial_partner_id, 0
            )

    def action_x4u_view_generators(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "x4u_generator.action_x4u_generator"
        )
        action["domain"] = [("customer_id", "=", self.commercial_partner_id.id)]
        action["context"] = {"create": False}
        return action
