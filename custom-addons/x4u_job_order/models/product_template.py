from odoo import _, api, models
from odoo.exceptions import ValidationError

# Spec v0.8 N1 / v0.9 C1: parts that go in and out by their serial, each valued at its own price.
SERIAL_CATEGORIES = ("x4u_setup_base.categ_engines", "x4u_setup_base.categ_ckd")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _x4u_serial_categories(self):
        return [categ for categ in (self.env.ref(xmlid, raise_if_not_found=False) for xmlid in SERIAL_CATEGORIES) if categ]

    @api.model
    def _x4u_serial_category(self, category):
        """An engine or a CKD category (or one under it)."""
        path = category.parent_path or ""
        return bool(category) and any(path.startswith(categ.parent_path) for categ in self._x4u_serial_categories())

    def _x4u_by_serial(self):
        """An engine or a CKD: tracked and valued by its serial."""
        self.ensure_one()
        return self._x4u_serial_category(self.categ_id)

    @api.depends("tracking", "x4u_is_generator", "categ_id")
    def _compute_lot_valuated(self):
        """Each generator keeps its own value (parts + overhead, spec v0.4 V5), and each engine and
        CKD what was paid for it (spec v0.8 N1, v0.9 C1)."""
        super()._compute_lot_valuated()
        for template in self:
            if template.tracking == "serial" and (template.x4u_is_generator or template._x4u_by_serial()):
                template.lot_valuated = True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            categ = self.env["product.category"].browse(vals.get("categ_id"))
            # Odoo fills the default "none" in before this point (a product.product create).
            if vals.get("is_storable") and vals.get("tracking", "none") == "none" and self._x4u_serial_category(categ):
                vals["tracking"] = "serial"
        return super().create(vals_list)

    @api.onchange("categ_id", "is_storable")
    def _onchange_x4u_engine_serial(self):
        if self.is_storable and self._x4u_by_serial():
            self.tracking = "serial"

    @api.constrains("categ_id", "tracking", "is_storable")
    def _check_x4u_engine_serial(self):
        for template in self:
            if template.is_storable and template.tracking != "serial" and template._x4u_by_serial():
                raise ValidationError(
                    _(
                        "%s is an engine or a CKD: each one is tracked by its serial number "
                        "(Tracking: By Unique Serial Number).",
                        template.display_name,
                    )
                )
