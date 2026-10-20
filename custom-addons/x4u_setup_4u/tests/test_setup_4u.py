import re

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSetup4U(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )

    def test_numbering(self):
        partner = self.env["res.partner"].create({"name": "X4U Test Customer"})
        order = self.env["sale.order"].create({"partner_id": partner.id})
        self.assertRegex(order.name, r"^4U-SO-\d{3,}$")
        product = self.env["product.product"].create({"name": "X4U Test Assembly", "is_storable": True})
        part = self.env["product.product"].create({"name": "X4U Test Component", "is_storable": True})
        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": product.product_tmpl_id.id,
                "bom_line_ids": [Command.create({"product_id": part.id, "product_qty": 1})],
            }
        )
        production = self.env["mrp.production"].create({"product_id": product.id})
        self.assertRegex(production.name, r"^4U-PO-\d{3,}$")
        # Purchase orders keep Odoo's own numbering, apart from the generator Job Order.
        purchase = self.env["purchase.order"].create({"partner_id": partner.id})
        self.assertFalse(re.match(r"^4U-PO-", purchase.name))

    def test_generator_flow_routes(self):
        self.assertEqual(self.warehouse.manufacture_steps, "pbm")
        self.assertTrue(self.warehouse.pbm_type_id.active)
        mto = self.env.ref("stock.route_warehouse0_mto")
        self.assertTrue(mto.active)
        self.assertEqual(self.warehouse.pbm_mto_pull_id.procure_method, "mts_else_mto")
        to_customer = mto.rule_ids.filtered(
            lambda rule: rule.location_dest_id.usage == "customer"
            and rule.picking_type_id.warehouse_id == self.warehouse
        )
        self.assertEqual(set(to_customer.mapped("procure_method")), {"make_to_order"})

    def test_sales_defaults(self):
        company = self.env.company
        template = self.env.ref("x4u_setup_4u.template_generator_supply")
        self.assertEqual(company.quotation_validity_days, 30)
        self.assertEqual(company.sale_order_template_id, template)
        self.assertEqual(template.number_of_days, 30)
        self.assertEqual(
            template.sale_order_template_option_ids.product_id.mapped("name"),
            ["Installation", "Transport", "Commissioning"],
        )
        self.assertEqual(self.env.ref("sales_team.team_sales_department").name, "4U Sales")
        currencies = {
            xmlid: self.env.ref("x4u_setup_4u." + xmlid).currency_id.name
            for xmlid in ("pricelist_standard", "pricelist_contractors", "pricelist_distributors", "pricelist_export")
        }
        self.assertEqual(
            currencies,
            {"pricelist_standard": "AED", "pricelist_contractors": "AED", "pricelist_distributors": "AED", "pricelist_export": "USD"},
        )
