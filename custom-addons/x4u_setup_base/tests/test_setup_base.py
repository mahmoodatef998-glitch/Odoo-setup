from odoo import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestSetupBase(TransactionCase):
    def test_settings_applied(self):
        employee = self.env.ref("base.group_user")
        for xmlid in (
            "uom.group_uom",
            "product.group_product_variant",
            "product.group_product_pricelist",
            "sale.group_discount_per_so_line",
            "sale_management.group_sale_order_template",
            "account.group_delivery_invoice_address",
            "sale.group_proforma_sales",
            "stock.group_production_lot",
            "stock.group_stock_multi_locations",
            "stock.group_adv_location",
        ):
            self.assertIn(self.env.ref(xmlid), employee.trans_implied_ids, xmlid)
        self.assertTrue(self.env.ref("base.USD").active)
        self.assertEqual(self.env.company.po_double_validation, "two_step")
        self.assertEqual(self.env.company.po_double_validation_amount, 0.0)

    def test_every_purchase_order_waits_for_approval(self):
        buyer = new_test_user(
            self.env, login="x4u_buyer", groups="base.group_user,purchase.group_purchase_user"
        )
        vendor = self.env["res.partner"].create({"name": "X4U Test Vendor"})
        product = self.env["product.product"].create({"name": "X4U Test Part"})
        order = self.env["purchase.order"].create(
            {
                "partner_id": vendor.id,
                "order_line": [
                    Command.create({"product_id": product.id, "product_qty": 1, "price_unit": 1.0})
                ],
            }
        )
        order.with_user(buyer).button_confirm()
        self.assertEqual(order.state, "to approve")

    def test_categories_units_attributes(self):
        ref = self.env.ref
        components = ref("x4u_setup_base.categ_components")
        for xmlid in ("categ_engines", "categ_alternators", "categ_bodies"):
            self.assertEqual(ref("x4u_setup_base." + xmlid).parent_id, components)
        roll = ref("x4u_setup_base.uom_roll_91m")
        self.assertEqual(roll._compute_quantity(1.0, ref("uom.product_uom_meter")), 91.0)
        for xmlid, values in (
            ("attr_enclosure", ["Open", "Canopy"]),
            ("attr_alternator", ["AQT", "Leroy-Somer", "Stamford"]),
        ):
            attribute = ref("x4u_setup_base." + xmlid)
            self.assertEqual(attribute.create_variant, "dynamic")
            self.assertEqual(attribute.value_ids.mapped("name"), values)

    def test_crm_stages_and_payment_terms(self):
        stages = [self.env.ref("crm.stage_lead%d" % i).name for i in range(1, 5)]
        self.assertEqual(stages, ["New", "Quotation Sent", "Negotiation", "Won"])
        for xmlid, days in (
            ("payment_term_advance_100", [0]),
            ("payment_term_50_50", [0, 0]),
            ("payment_term_60_days", [60]),
            ("payment_term_90_days", [90]),
            ("payment_term_lc_sight", [0]),
        ):
            term = self.env.ref("x4u_setup_base." + xmlid)
            self.assertEqual(sum(term.line_ids.mapped("value_amount")), 100.0, xmlid)
            self.assertEqual(term.line_ids.mapped("nb_days"), days, xmlid)
