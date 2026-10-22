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

    def test_sales_settings_v2(self):
        """Lock confirmed sales, credit limit, no automatic lead enrichment (01-sales.md D9, D10, S4)."""
        self.assertIn(self.env.ref("sale.group_auto_done_setting"), self.env.ref("base.group_user").trans_implied_ids)
        self.assertTrue(self.env.company.account_use_credit_limit)
        cron = self.env.ref("crm_iap_enrich.ir_cron_lead_enrichment", raise_if_not_found=False)
        if cron:
            self.assertFalse(cron.active)

    def test_unused_defaults_archived(self):
        Term = self.env["account.payment.term"]
        kept = Term.search([("company_id", "in", [self.env.company.id, False])]).mapped("name")
        for name in ("Immediate Payment", "30 Days", "100% Advance", "60 Days", "LC at Sight"):
            self.assertIn(name, kept)
        for name in ("15 Days", "21 Days", "45 Days", "2/7 Net 30"):
            self.assertNotIn(name, kept)
        reasons = self.env["crm.lost.reason"].search([]).mapped("name")
        self.assertIn("Price too high", reasons)
        self.assertIn("No response from the customer", reasons)
        self.assertNotIn("We don't have people/skills", reasons)

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

    def test_approver_gets_a_todo(self):
        """Each order to approve is a to-do for the approvers, closed when approved or cancelled (guide R2)."""
        buyer = new_test_user(self.env, login="x4u_buyer_todo", groups="base.group_user,purchase.group_purchase_user")
        approver = new_test_user(self.env, login="x4u_approver", groups="base.group_user,purchase.group_purchase_manager")
        other_approver = new_test_user(self.env, login="x4u_approver_2", groups="base.group_user,purchase.group_purchase_manager")
        approval = self.env.ref("x4u_setup_base.mail_activity_type_po_approval")
        vendor = self.env["res.partner"].create({"name": "X4U Test Vendor"})
        product = self.env["product.product"].create({"name": "X4U Test Part"})
        first, second = self.env["purchase.order"].create(
            [
                {
                    "partner_id": vendor.id,
                    "order_line": [Command.create({"product_id": product.id, "product_qty": 1, "price_unit": 100.0})],
                }
                for _i in range(2)
            ]
        )

        def todo(order):
            return order.activity_ids.filtered(lambda a: a.activity_type_id == approval)

        (first | second).with_user(buyer).button_confirm()
        for order in (first, second):
            self.assertTrue((approver | other_approver) <= todo(order).user_id)
            self.assertNotIn(buyer, todo(order).user_id)
            self.assertIn(order.name, todo(order)[:1].summary)
        # Asking again doesn't add a second to-do.
        first._x4u_ask_approval()
        self.assertEqual(len(todo(first).filtered(lambda a: a.user_id == approver)), 1)

        first.with_user(approver).button_approve()
        self.assertEqual(first.state, "purchase")
        self.assertFalse(todo(first))
        self.assertTrue(
            first.message_ids.filtered(lambda m: m.author_id == approver.partner_id and m.mail_activity_type_id == approval)
        )

        second.with_user(buyer).button_cancel()
        self.assertFalse(todo(second))

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
