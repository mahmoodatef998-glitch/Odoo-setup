import copy

from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged

ENTRY = {
    "code": "4U-T300",
    "brand": "Cummins",
    "engine": "6LTAA9.5-G1",
    "primeKva": 300,
    "standbyKva": 330,
    "url": "https://www.4ugenerators.com/en/models/4u-c300",
    "properties": [
        ["Standby (ESP)", "330 kVA / 264 kW"],
        ["Prime (PRP)", "300 kVA / 240 kW"],
        ["Voltage / frequency", "400/230 V · 3-phase · 50 Hz · 1500 rpm"],
        ["Power factor", "0.8"],
        ["Make / model", "Cummins 6LTAA9.5-G1"],
        ["Cylinders", "6 in-line"],
        ["Aspiration", "Turbocharged, air-to-air charge cooled"],
        ["Cooling", "Water cooled, radiator for 50 °C ambient"],
        ["Leroy-Somer frame", "TAL-A46-F"],
        ["Stamford frame", "HCI444D/S4L1DD41"],
        ["Base fuel tank", "625 L"],
        ["Controller", "Deep Sea DSE6120 · auto start / AMF"],
        ["Main breaker", "3-pole LS MCCB"],
        ["Warranty", "12 months or 1,000 running hours, whichever first"],
    ],
    "prices": {
        "4U": {"currency": "AED", "uae": 90000.0, "export": 88000.0},
        "Leroy-Somer": {"currency": "AED", "uae": 100000.0, "export": 97000.0},
    },
}


@tagged("post_install", "-at_install")
class TestGeneratorCatalog(TransactionCase):
    """x4u_generator_datasheet spec §8: the models from the datasheets and the 2026 price lists."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Catalog = cls.env["x4u.generator.catalog"]
        cls.customer = cls.env["res.partner"].create({"name": "X4U Test Catalog Customer"})

    def _template(self, code="4U-T300"):
        return self.env["product.template"].search([("x4u_model_code", "=", code)])

    def _variant(self, template, choice):
        return template.product_variant_ids.filtered(lambda p: p._x4u_alternator_choice() == choice)

    def _price(self, variant, xmlid):
        return self.env.ref(xmlid)._get_product_price(variant, 1.0)

    # T1, T7: a model with its alternators, code, datasheet and BoM
    def test_import_model(self):
        report = self.Catalog._x4u_import([copy.deepcopy(ENTRY)])
        template = self._template()
        self.assertEqual(report["models"], 1)
        self.assertEqual(self.env.ref("x4u_setup_base.attr_alternator_aqt").name, "4U")
        self.assertEqual(
            sorted(template.product_variant_ids.mapped(lambda p: p._x4u_alternator_choice())), ["4U", "Leroy-Somer", "Stamford"]
        )
        self.assertEqual(set(template.product_variant_ids.mapped("default_code")), {"4U-T300"})
        self.assertTrue(template.x4u_is_generator and template.tracking == "serial")
        self.assertEqual(template.categ_id, self.env.ref("x4u_setup_base.categ_generators"))
        self.assertEqual(len(template.x4u_datasheet_line_ids), len(ENTRY["properties"]))
        self.assertEqual(template.x4u_datasheet_code, "4U-DS-T300")
        lines = template.bom_ids.bom_line_ids
        self.assertIn("ENG-6LTAA9.5-G1", lines.product_id.mapped("default_code"))
        leroy = lines.filtered(lambda l: l.product_id.default_code == "ALT-TAL-A46-F")
        self.assertEqual(leroy.bom_product_template_attribute_value_ids.name, "Leroy-Somer")
        engine = lines.filtered(lambda l: l.product_id.default_code == "ENG-6LTAA9.5-G1").product_id
        self.assertEqual(engine.tracking, "serial", "an engine is tracked by its serial")

    # T2: the UAE and export lists; Export (USD) follows Export (AED)
    def test_prices(self):
        entry = copy.deepcopy(ENTRY)
        entry["code"] = "4U-T301"
        perkins = copy.deepcopy(ENTRY)
        perkins.update(code="4U-T302", brand="Perkins", prices={"4U": {"currency": "GBP", "uae": 25000.0, "export": 24000.0}})
        self.Catalog._x4u_import([entry, perkins])
        leroy = self._variant(self._template("4U-T301"), "Leroy-Somer")
        self.assertEqual(self._price(leroy, "x4u_setup_4u.pricelist_standard"), 100000.0)
        self.assertEqual(self._price(leroy, "x4u_job_order.pricelist_export_aed"), 97000.0)
        usd = self.env.ref("x4u_setup_4u.pricelist_export")
        expected = self.env.ref("base.AED")._convert(97000.0, usd.currency_id, self.env.company, self.env.cr.now().date())
        self.assertAlmostEqual(self._price(leroy, "x4u_setup_4u.pricelist_export"), expected, places=2)
        p4u = self._variant(self._template("4U-T302"), "4U")
        gbp = self.env.ref("base.GBP")._convert(24000.0, self.env.ref("base.AED"), self.env.company, self.env.cr.now().date())
        self.assertAlmostEqual(self._price(p4u, "x4u_job_order.pricelist_export_aed"), gbp, places=2)
        self.assertFalse(self._price(self._variant(self._template("4U-T301"), "Stamford"), "x4u_setup_4u.pricelist_standard"))

    # T3: a second import updates the model, its datasheet and prices; nothing is duplicated
    def test_reimport(self):
        self.Catalog._x4u_import([copy.deepcopy(ENTRY)])
        entry = copy.deepcopy(ENTRY)
        entry["standbyKva"] = 335
        entry["properties"] = entry["properties"][:3]
        entry["prices"]["4U"]["uae"] = 99000.0
        self.Catalog._x4u_import([entry])
        template = self._template()
        self.assertEqual(len(template), 1)
        self.assertEqual(template.x4u_kva_standby, 335)
        self.assertEqual(len(template.x4u_datasheet_line_ids), 3)
        self.assertEqual(len(template.product_variant_ids), 3)
        self.assertEqual(self._price(self._variant(template, "4U"), "x4u_setup_4u.pricelist_standard"), 99000.0)

    # T4 (QT 1112): the line's description, the extras in the price and the text, the price editable
    def test_quotation_line(self):
        self.Catalog._x4u_import([copy.deepcopy(ENTRY)])
        variant = self._variant(self._template(), "Leroy-Somer")
        form = Form(self.env["sale.order"])
        form.partner_id = self.customer
        form.pricelist_id = self.env.ref("x4u_job_order.pricelist_export_aed")
        with form.order_line.new() as line:
            line.product_id = variant
            line.x4u_extras = "Water jacket heater and anti-condensation heater"
            line.x4u_extras_price = 3300
            line.discount = 5
        order = form.save()
        line = order.order_line
        self.assertEqual(line.price_unit, 100300.0, "the list price + 3,300 of extras, as in QT 1112")
        self.assertIn("Cummins 6LTAA9.5-G1 engine (6-cylinder in-line", line.name)
        self.assertIn("Leroy-Somer TAL-A46-F alternator", line.name)
        self.assertTrue(line.name.endswith("Water jacket heater and anti-condensation heater"))
        self.assertAlmostEqual(line.price_subtotal, 100300.0 * 0.95, places=2)
        with Form(order) as edit:
            with edit.order_line.edit(0) as row:
                row.price_unit = 100000.0
                row.x4u_extras_price = 3000
        self.assertEqual(order.order_line.price_unit, 99700.0, "a price typed by hand stays; the extras change moves it")

    # T5: Stamford has no list price: "As requested", and no PI before its price is typed
    def test_price_on_request(self):
        self.Catalog._x4u_import([copy.deepcopy(ENTRY)])
        order = self.env["sale.order"].create(
            {"partner_id": self.customer.id, "order_line": [(0, 0, {"product_id": self._variant(self._template(), "Stamford").id})]}
        )
        self.assertEqual(order.order_line.price_unit, 0.0)
        self.assertTrue(order.order_line._x4u_as_requested())
        with self.assertRaisesRegex(UserError, "price on request"):
            order.action_x4u_create_proforma()
