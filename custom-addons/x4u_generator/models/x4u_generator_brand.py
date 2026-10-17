from odoo import fields, models


class X4uGeneratorBrand(models.Model):
    _name = "x4u.generator.brand"
    _description = "Generator Engine / Alternator Brand"
    _order = "name"

    name = fields.Char(required=True)
    brand_type = fields.Selection(
        [
            ("engine", "Engine"),
            ("alternator", "Alternator"),
            ("both", "Engine & Alternator"),
        ],
        string="Type",
        required=True,
        default="engine",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "name_uniq",
            "unique(name)",
            "A generator brand with this name already exists.",
        ),
    ]
