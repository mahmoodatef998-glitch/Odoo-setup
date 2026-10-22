import re

from odoo import Command, fields
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
        # Prices are entered by hand: one pricelist per currency (01-sales.md D2).
        pricelists = {
            xmlid: self.env.ref("x4u_setup_4u." + xmlid) for xmlid in ("pricelist_standard", "pricelist_export")
        }
        self.assertEqual(
            {xmlid: (pl.name, pl.currency_id.name) for xmlid, pl in pricelists.items()},
            {"pricelist_standard": ("Standard", "AED"), "pricelist_export": ("Export", "USD")},
        )
        self.assertEqual(pricelists["pricelist_standard"].display_name, "Standard (AED)")
        self.assertEqual({pl.company_id for pl in pricelists.values()}, {company})
        self.assertFalse(self.env.ref("x4u_setup_4u.pricelist_contractors", raise_if_not_found=False))

    def test_invoice_numbers_carry_the_company(self):
        """4U-INV-<year>-0001 for invoices, 4U-CN-<year>-0001 for credit notes (06-accounting.md)."""
        self.assertEqual(self.env.company.x4u_document_prefix, "4U")
        # A journal with no invoice yet, so the first number of the year is built here
        # (on a database with demo data the default journal already has numbers).
        journal = self.env["account.journal"].create({"name": "X4U Test Sales", "type": "sale", "code": "X4UT"})
        partner = self.env["res.partner"].create({"name": "X4U Test Customer"})
        product = self.env.ref("x4u_setup_4u.product_installation")

        def post(move_type):
            move = self.env["account.move"].create(
                {
                    "move_type": move_type,
                    "journal_id": journal.id,
                    "partner_id": partner.id,
                    "invoice_date": fields.Date.today(),
                    "invoice_line_ids": [Command.create({"product_id": product.id, "quantity": 1, "price_unit": 100.0})],
                }
            )
            move.action_post()
            return move

        year = fields.Date.today().year
        first, second = post("out_invoice"), post("out_invoice")
        self.assertEqual(first.name, "4U-INV-%d-0001" % year)
        self.assertEqual(second.name, "4U-INV-%d-0002" % year)
        self.assertEqual(post("out_refund").name, "4U-CN-%d-0001" % year)

    def test_default_sales_tax_sharjah(self):
        """5% Sharjah until the accountant decides (01-sales.md D12), on the company and our services."""
        company = self.env.company
        sharjah = self.env.ref("account.%s_uae_sale_tax_5_sharjah" % company.id, raise_if_not_found=False)
        if not sharjah:
            self.skipTest("Company without the UAE chart of accounts")
        self.assertEqual(company.account_sale_tax_id, sharjah)
        installation = self.env.ref("x4u_setup_4u.product_installation")
        self.assertEqual(installation.taxes_id.filtered(lambda t: t.company_id == company), sharjah)

    def test_single_default_pricelist(self):
        """Standard is the default pricelist; saving Settings doesn't bring Odoo's back."""
        Pricelist = self.env["product.pricelist"].with_context(active_test=False)
        standard = self.env.ref("x4u_setup_4u.pricelist_standard")
        before = Pricelist.search([])
        self.env["res.company"]._activate_or_create_pricelists()
        self.assertEqual(Pricelist.search([]), before)
        partner = self.env["res.partner"].create({"name": "X4U Test Customer"})
        self.assertEqual(partner.property_product_pricelist, standard)
        ours = self.env["ir.model.data"].search(
            [("module", "=", "x4u_setup_4u"), ("model", "=", "product.pricelist")]
        ).mapped("res_id")
        unused_extra = Pricelist.search(
            [("id", "not in", ours), ("company_id", "=", self.env.company.id), ("item_ids", "=", False)]
        )
        unused_extra -= self.env["sale.order"].search([("pricelist_id", "in", unused_extra.ids)]).pricelist_id
        self.assertFalse(unused_extra)
