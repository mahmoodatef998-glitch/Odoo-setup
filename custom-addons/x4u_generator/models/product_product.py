import re

from odoo import models

# Template fields checked together by the generator product rule (spec R1).
GENERATOR_RULE_FIELDS = (
    "x4u_is_generator",
    "x4u_kva_prime",
    "type",
    "is_storable",
    "tracking",
)


def _clean(value):
    return " ".join((value or "").replace("·", " ").split())


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _x4u_alternator_choice(self):
        """The variant's Alternator value (4U, Leroy-Somer, Stamford), or ''."""
        self.ensure_one()
        values = self.product_template_attribute_value_ids.filtered(
            lambda v: (v.attribute_id.name or "").strip().lower() == "alternator"
        )
        return values[:1].name or ""

    def _x4u_quote_description(self):
        """Spec x4u_generator_datasheet §3 / QT 1112: the quotation text of a generator, from its
        datasheet and the variant's alternator. Empty for a product without a datasheet."""
        self.ensure_one()
        template = self.product_tmpl_id
        data = {line.name: line.value for line in template.x4u_datasheet_line_ids}
        if not data:
            return ""
        brand = template.x4u_engine_brand_id.name or ""
        choice = self._x4u_alternator_choice()
        if choice.startswith("Leroy") and template.x4u_leroy_frame:
            alternator = "Leroy-Somer %s alternator" % template.x4u_leroy_frame
        elif choice.startswith("Stamford") and template.x4u_stamford_frame:
            alternator = "Stamford %s alternator" % template.x4u_stamford_frame
        elif choice:
            alternator = "%s alternator" % ("4U Power" if choice in ("4U", "AQT") else choice)
        else:
            alternator = "4U · Leroy-Somer | Stamford alternator"
        cylinders = re.sub(r"^(\d+) ", r"\1-cylinder ", data.get("Cylinders") or "")
        engine_detail = ", ".join(x for x in (cylinders, (data.get("Aspiration") or "").lower()) if x)
        cooling = (data.get("Cooling") or "").split(",")[0].lower()
        controller = data.get("Controller") or template.x4u_controller
        lines = [
            "Brand new, heavy-duty industrial grade %s diesel generator set, ready to run." % brand,
            "%s kVA Prime / %s kVA Standby | %s | %s Power Factor." % (
                "%g" % template.x4u_kva_prime, "%g" % template.x4u_kva_standby,
                " | ".join(_clean(part) for part in (data.get("Voltage / frequency") or "").split("·")),
                data.get("Power factor") or "0.8",
            ),
            "Original %s engine%s%s, directly coupled to a %s." % (
                data.get("Make / model") or template.x4u_engine_model or "",
                " (%s)" % engine_detail if engine_detail else "",
                ", %s" % cooling if cooling else "",
                alternator,
            ),
        ]
        if controller:
            lines.append("%s control module with full monitoring and protection." % _clean(controller).replace(" auto start", " auto-start"))
        lines.append("%s main circuit breaker, batteries and battery charger, base frame fuel tank%s." % (
            data.get("Main breaker") or "Main", " (%s)" % data["Base fuel tank"] if data.get("Base fuel tank") else ""))
        lines.append("Packaged inside a sound-attenuated, weatherproof silent canopy%s." % (
            " (%s at 7 m)" % data["Noise @ 7 m"] if data.get("Noise @ 7 m") else ""))
        return "\n".join(lines)

    def get_product_multiline_description_sale(self):
        """A generator with a datasheet: its name, then its quotation text (QT 1112)."""
        description = self._x4u_quote_description() if len(self) == 1 else ""
        if not description:
            return super().get_product_multiline_description_sale()
        return "%s\n%s" % (self.display_name, description)

    def write(self, vals):
        # The ORM writes inherited template fields one by one, so the R1
        # constraint would see "generator without kVA" halfway through.
        if self and {"x4u_is_generator", "x4u_kva_prime"} & vals.keys():
            vals = dict(vals)
            self.product_tmpl_id.write(
                {name: vals.pop(name) for name in GENERATOR_RULE_FIELDS if name in vals}
            )
        return super().write(vals)
