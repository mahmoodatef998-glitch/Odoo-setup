from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    x4u_is_generator = fields.Boolean(
        string="Is Generator",
        help="Each serial number of this product gets a Generator Card.",
    )
    x4u_kva_prime = fields.Float(string="Prime Rating (kVA)")
    x4u_kva_standby = fields.Float(string="Standby Rating (kVA)")
    x4u_engine_brand_id = fields.Many2one(
        "x4u.generator.brand",
        string="Engine Brand",
        domain="[('brand_type', 'in', ('engine', 'both'))]",
    )
    x4u_engine_model = fields.Char(string="Engine Model")
    x4u_alternator_brand_id = fields.Many2one(
        "x4u.generator.brand",
        string="Alternator Brand",
        domain="[('brand_type', 'in', ('alternator', 'both'))]",
    )
    x4u_alternator_model = fields.Char(string="Alternator Model")
    x4u_warranty_months = fields.Integer(string="Warranty (Months)", default=12)
    x4u_warranty_hours = fields.Float(
        string="Warranty (Running Hours)", help="0 means no running-hours limit."
    )
    x4u_warranty_max_delivery_months = fields.Integer(
        string="Max Warranty from Delivery (Months)",
        help="Optional cap: the warranty also ends this many months after delivery, "
        "whichever comes first. 0 means no cap.",
    )

    @api.onchange("x4u_is_generator")
    def _onchange_x4u_is_generator(self):
        if self.x4u_is_generator:
            self.type = "consu"
            self.is_storable = True
            self.tracking = "serial"

    @api.constrains("x4u_is_generator", "is_storable", "tracking", "x4u_kva_prime")
    def _check_x4u_generator_product(self):
        for template in self.filtered("x4u_is_generator"):
            if not template.is_storable or template.tracking != "serial":
                raise ValidationError(
                    _(
                        "Generator product %s must track inventory by unique "
                        "serial number.",
                        template.display_name,
                    )
                )
            if template.x4u_kva_prime <= 0:
                raise ValidationError(
                    _(
                        "Generator product %s needs a prime rating (kVA) greater "
                        "than zero.",
                        template.display_name,
                    )
                )
