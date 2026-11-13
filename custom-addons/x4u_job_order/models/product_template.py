from odoo import _, api, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _x4u_is_engine(self):
        """Spec v0.8 N1: a product of the Engines category (or one under it)."""
        self.ensure_one()
        engines = self.env.ref("x4u_setup_base.categ_engines", raise_if_not_found=False)
        path = self.categ_id.parent_path or ""
        return bool(engines and path.startswith(engines.parent_path))

    @api.depends("tracking", "x4u_is_generator", "categ_id")
    def _compute_lot_valuated(self):
        """Each generator keeps its own value (parts + overhead, spec v0.4 V5), and each engine
        what was paid for it (spec v0.8 N1)."""
        super()._compute_lot_valuated()
        for template in self:
            if template.tracking == "serial" and (template.x4u_is_generator or template._x4u_is_engine()):
                template.lot_valuated = True

    @api.model_create_multi
    def create(self, vals_list):
        engines = self.env.ref("x4u_setup_base.categ_engines", raise_if_not_found=False)
        for vals in vals_list:
            categ = self.env["product.category"].browse(vals.get("categ_id"))
            # Odoo fills the default "none" in before this point (a product.product create).
            if engines and categ and vals.get("is_storable") and vals.get("tracking", "none") == "none" and (
                categ.parent_path or ""
            ).startswith(engines.parent_path):
                vals["tracking"] = "serial"
        return super().create(vals_list)

    @api.onchange("categ_id", "is_storable")
    def _onchange_x4u_engine_serial(self):
        if self.is_storable and self._x4u_is_engine():
            self.tracking = "serial"

    @api.constrains("categ_id", "tracking", "is_storable")
    def _check_x4u_engine_serial(self):
        for template in self:
            if template.is_storable and template.tracking != "serial" and template._x4u_is_engine():
                raise ValidationError(
                    _("%s is an engine: every engine is tracked by its serial number (Tracking: By Unique Serial Number).", template.display_name)
                )
