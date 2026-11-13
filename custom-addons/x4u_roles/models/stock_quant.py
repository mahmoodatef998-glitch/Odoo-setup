from odoo import _, models
from odoo.exceptions import AccessError


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def action_apply_inventory(self):
        # x4u_job_order spec v0.8 N2: Purchasing receives purchases; stock counts stay with the Storekeeper.
        user = self.env.user
        if user.has_group("x4u_roles.group_x4u_receipts_only") and not user.has_group("stock.group_stock_manager"):
            raise AccessError(_("Stock counts are applied by the Storekeeper. Purchasing validates receipts only."))
        return super().action_apply_inventory()
