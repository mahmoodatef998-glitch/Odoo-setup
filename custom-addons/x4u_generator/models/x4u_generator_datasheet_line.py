from odoo import fields, models

# Spec x4u_generator_datasheet §3: the datasheet's sections, in the website's order. A line the
# website adds later lands in "Other" until it is placed here.
SECTIONS = [
    ("ratings", "Ratings"),
    ("engine", "Engine"),
    ("alternator", "Alternator"),
    ("fuel", "Fuel consumption"),
    ("dimensions", "Dimensions & weight"),
    ("control", "Control & protection"),
    ("warranty", "Warranty"),
    ("other", "Other"),
]
SECTION_OF = {
    "Standby (ESP)": "ratings", "Prime (PRP)": "ratings", "Voltage / frequency": "ratings",
    "Power factor": "ratings", "Other voltages": "ratings",
    "Make / model": "engine", "Cylinders": "engine", "Displacement": "engine", "Bore × stroke": "engine",
    "Aspiration": "engine", "Governing": "engine", "Cooling": "engine", "Coolant capacity": "engine",
    "Lube oil capacity": "engine",
    "Make": "alternator", "Leroy-Somer frame": "alternator", "Stamford frame": "alternator", "Type": "alternator",
    "Insulation / protection": "alternator", "Voltage regulation": "alternator",
    "50 % prime load": "fuel", "75 % prime load": "fuel", "100 % prime load": "fuel", "Standby rating": "fuel",
    "Fuel consumption": "fuel",
    "Open set (L × W × H)": "dimensions", "Open set weight": "dimensions", "Silent canopy (L × W × H)": "dimensions",
    "Canopy weight": "dimensions", "Container": "dimensions", "Containerised weight": "dimensions",
    "Base fuel tank": "dimensions", "Noise @ 7 m": "dimensions",
    "Controller": "control", "Main breaker": "control", "Shutdowns & alarms": "control",
    "Warranty": "warranty",
}


class X4uGeneratorDatasheetLine(models.Model):
    """Spec x4u_generator_datasheet §3: one line of a model's datasheet, as on the website."""

    _name = "x4u.generator.datasheet.line"
    _description = "Generator Datasheet Line"
    _order = "template_id, sequence, id"

    template_id = fields.Many2one("product.template", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    section = fields.Selection(SECTIONS, required=True, default="other")
    name = fields.Char(string="Item", required=True)
    value = fields.Char(required=True)
