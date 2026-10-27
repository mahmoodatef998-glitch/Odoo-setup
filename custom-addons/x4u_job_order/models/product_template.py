from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.depends("tracking", "x4u_is_generator")
    def _compute_lot_valuated(self):
        """Each generator keeps its own value (parts + overhead, spec v0.4 V5)."""
        super()._compute_lot_valuated()
        for template in self:
            if template.x4u_is_generator and template.tracking == "serial":
                template.lot_valuated = True
