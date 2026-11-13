from odoo import _, models
from odoo.exceptions import AccessError


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def action_x4u_deliver_materials(self):
        # x4u_job_order spec v0.8 N2: Purchasing receives purchases; the parts go to the factory
        # with the Storekeeper.
        user = self.env.user
        if user.has_group("x4u_roles.group_x4u_receipts_only") and not user.has_group("stock.group_stock_manager"):
            raise AccessError(_("Deliver Materials is the Storekeeper's. Purchasing validates receipts only."))
        return super().action_x4u_deliver_materials()
