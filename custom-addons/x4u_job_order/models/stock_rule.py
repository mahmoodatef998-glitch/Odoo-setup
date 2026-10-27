from odoo import api, models


class StockRule(models.Model):
    _inherit = "stock.rule"

    @api.model
    def _run_manufacture(self, procurements):
        """One Job Order per generator (spec v0.4 V8): a sale of 3 opens 3 Job Orders,
        each with its own serial, parts and flag. Odoo splits by "batch_size"."""
        for procurement, _rule in procurements:
            if procurement.product_id.x4u_is_generator:
                procurement.values["batch_size"] = 1
        return super()._run_manufacture(procurements)
