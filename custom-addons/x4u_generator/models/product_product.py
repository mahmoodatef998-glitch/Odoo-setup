from odoo import models

# Template fields checked together by the generator product rule (spec R1).
GENERATOR_RULE_FIELDS = (
    "x4u_is_generator",
    "x4u_kva_prime",
    "type",
    "is_storable",
    "tracking",
)


class ProductProduct(models.Model):
    _inherit = "product.product"

    def write(self, vals):
        # The ORM writes inherited template fields one by one, so the R1
        # constraint would see "generator without kVA" halfway through.
        if self and {"x4u_is_generator", "x4u_kva_prime"} & vals.keys():
            vals = dict(vals)
            self.product_tmpl_id.write(
                {name: vals.pop(name) for name in GENERATOR_RULE_FIELDS if name in vals}
            )
        return super().write(vals)
